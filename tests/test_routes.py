import csv
import pytest
import os
from io import BytesIO, StringIO
from zipfile import ZipFile
from fastapi.testclient import TestClient
from app import app

# Bloco auxiliar de monkeypatch.
def fake_list_shared_items(url):
    # Retorna itens com nomes previsiveis.
    return [
        {"name": "ABC_branco.jpg", "webUrl": "u1"},
        {"name": "ABC_ambient.jpg", "webUrl": "u2"},
        {"name": "ABC_medida.jpg", "webUrl": "u3"},
    ]


def test_photos_endpoint(monkeypatch):
    monkeypatch.setattr('catalog.onedrive.list_shared_items', fake_list_shared_items)
    monkeypatch.setattr('catalog.onedrive.resolve_local_products_root', lambda: None)
    client = TestClient(app)
    rv = client.get('/catalog/photos', params={
        'shareUrl': 'https://example.com/share',
        'code': 'ABC'
    })
    assert rv.status_code == 200
    data = rv.json()
    assert data['white_background'] == 'u1'
    assert data['ambient'] == 'u2'
    assert data['measures'] == 'u3'


def test_photos_missing_param():
    client = TestClient(app)
    rv = client.get('/catalog/photos')
    assert rv.status_code == 400
    assert 'error' in rv.json()


def test_spa_blocks_path_traversal():
    client = TestClient(app)
    for path in ('/..%2Fapp.py', '/%2e%2e%2fapp.py'):
        rv = client.get(path)
        assert rv.status_code == 200
        assert rv.headers.get('content-type', '').startswith('text/html')
        assert 'from fastapi import FastAPI' not in rv.text


def test_photos_no_credentials(monkeypatch):
    # Se variaveis de ambiente do Azure nao estiverem definidas, a rota deve
    # retornar lista de fotos sem falhar com HTTP 500.
    monkeypatch.delenv('AZURE_CLIENT_ID', raising=False)
    monkeypatch.delenv('AZURE_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('AZURE_TENANT_ID', raising=False)
    monkeypatch.setattr('catalog.onedrive.resolve_local_products_root', lambda: None)
    client = TestClient(app)
    rv = client.get('/catalog/photos', params={'shareUrl': 'x', 'code': 'y'})
    assert rv.status_code == 200
    data = rv.json()
    # Deve retornar placeholders contendo o codigo.
    assert 'white_background' in data and 'ambient' in data and 'measures' in data
    assert 'y' in data['white_background']
    assert data['white_background'].startswith('https://placehold.co/')


def test_product_images_route(monkeypatch):
    # Simula resposta do OneDrive.
    monkeypatch.setattr('catalog.onedrive.find_local_images_for_code', lambda code: [])
    monkeypatch.setattr('catalog.onedrive.resolve_local_products_root', lambda: None)
    monkeypatch.setattr('catalog.onedrive.find_images_for_code', lambda shareUrl, code: [
        {'name': f'{code}.jpg', 'variant': 0, 'url': 'u1'},
        {'name': f'{code}-1.png', 'variant': 1, 'url': 'u2'},
    ])
    client = TestClient(app)
    rv = client.get('/catalog/produtos/6649/imagens', params={'shareUrl': 'https://fake'})
    assert rv.status_code == 200
    data = rv.json()
    assert data['codigo'] == '6649'
    assert len(data['imagens']) == 2
    assert data['imagens'][1]['variant'] == 1
    # Parametro shareUrl ausente deve retornar 400.
    rv2 = client.get('/catalog/produtos/6649/imagens')
    assert rv2.status_code == 400


def test_product_images_route_prefers_local(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.find_local_images_for_code',
        lambda code: [{'name': f'{code}.jpg', 'variant': 0, 'url': 'local-u1'}]
    )
    monkeypatch.setattr(
        'catalog.onedrive.find_images_for_code',
        lambda shareUrl, code: (_ for _ in ()).throw(RuntimeError('should not call graph'))
    )
    client = TestClient(app)
    rv = client.get('/catalog/produtos/6649/imagens')
    assert rv.status_code == 200
    data = rv.json()
    assert data['codigo'] == '6649'
    assert data['imagens'][0]['url'] == 'local-u1'


def test_product_images_local_mode_without_photos(monkeypatch):
    monkeypatch.setattr('catalog.onedrive.find_local_images_for_code', lambda code: [])
    monkeypatch.setattr('catalog.onedrive.resolve_local_products_root', lambda: r'C:\Users\joao.silva\OneDrive\MARKETING\Catalogo')
    monkeypatch.setattr(
        'catalog.onedrive.find_images_for_code',
        lambda shareUrl, code: (_ for _ in ()).throw(RuntimeError('should not call graph'))
    )
    client = TestClient(app)
    rv = client.get('/catalog/produtos/6379/imagens')
    assert rv.status_code == 200
    assert rv.json() == {'codigo': '6379', 'imagens': []}


def test_local_products_route(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '5989',
                'Nome': 'Produto',
                'Categoria': 'ABAJUR',
                'VendaMes': 87,
                'Embalagem': '6',
                'CaixaMaster': '24',
            }
        ]
    )
    client = TestClient(app)
    rv = client.get('/catalog/local/produtos')
    assert rv.status_code == 200
    data = rv.json()
    assert isinstance(data, list)
    assert data[0]['Codigo'] == '5989'
    assert data[0]['VendaMes'] == 87
    assert data[0]['Embalagem'] == '6'
    assert data[0]['CaixaMaster'] == '24'
    assert rv.headers['etag'].startswith('"')
    assert rv.headers['cache-control'] == 'private, no-cache'

    not_modified = client.get(
        '/catalog/local/produtos',
        headers={'If-None-Match': rv.headers['etag']},
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b''


def test_representative_admin_routes_manage_users(monkeypatch, tmp_path):
    managed_path = tmp_path / "representatives.json"
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "env@example.com")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "env-secret")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "Equipe Ambiente")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_JSON", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_FILE", str(managed_path))

    client = TestClient(app)

    initial = client.get("/catalog/representatives")
    assert initial.status_code == 200
    initial_payload = initial.json()
    assert initial_payload["total_users"] == 1
    assert initial_payload["environment_users"] == 1
    assert initial_payload["managed_users"] == 0
    assert initial_payload["users"][0]["email"] == "env@example.com"
    assert initial_payload["users"][0]["managed"] is False

    created = client.put(
        "/catalog/representatives/rep@example.com",
        json={"email": "rep@example.com", "name": "Representante Recife", "password": "rep-secret"},
    )
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["created"] is True
    assert created_payload["managed_users"] == 1
    assert any(user["email"] == "rep@example.com" and user["managed"] for user in created_payload["users"])

    stored_payload = managed_path.read_text(encoding="utf-8")
    assert "rep@example.com" in stored_payload
    assert "rep-secret" not in stored_payload
    assert "password_hash" in stored_payload

    updated = client.put(
        "/catalog/representatives/rep@example.com",
        json={"email": "rep@example.com", "name": "Representante Nordeste"},
    )
    assert updated.status_code == 200
    assert updated.json()["created"] is False
    assert any(
        user["email"] == "rep@example.com" and user["name"] == "Representante Nordeste"
        for user in updated.json()["users"]
    )

    conflict = client.put(
        "/catalog/representatives/env@example.com",
        json={"email": "env@example.com", "name": "Duplicado", "password": "new-secret"},
    )
    assert conflict.status_code == 400
    assert conflict.json()["error"] == "Representative email is managed by environment configuration"

    deleted = client.delete("/catalog/representatives/rep@example.com")
    assert deleted.status_code == 200
    deleted_payload = deleted.json()
    assert deleted_payload["deleted"] is True
    assert deleted_payload["managed_users"] == 0
    assert all(user["email"] != "rep@example.com" for user in deleted_payload["users"])


def test_local_asset_route(monkeypatch, tmp_path):
    asset_path = tmp_path / "asset.jpg"
    asset_path.write_bytes(b"jpg")
    monkeypatch.setattr('catalog.onedrive.resolve_local_asset_path', lambda path: str(asset_path))
    client = TestClient(app)
    rv = client.get('/catalog/local/asset', params={'path': 'x'})
    assert rv.status_code == 200
    assert rv.content


def test_local_asset_route_blocks_non_image_files(monkeypatch, tmp_path):
    asset_path = tmp_path / "asset.txt"
    asset_path.write_text("not-an-image", encoding="utf-8")
    monkeypatch.setattr('catalog.onedrive.resolve_local_asset_path', lambda path: str(asset_path))
    client = TestClient(app)
    rv = client.get('/catalog/local/asset', params={'path': 'x'})
    assert rv.status_code == 403
    assert rv.json()["error"] == "unsupported asset type"


def test_local_asset_route_converts_tiff(monkeypatch):
    monkeypatch.setattr('catalog.onedrive.resolve_local_asset_path', lambda path: r'C:\fake\img.tif')
    monkeypatch.setattr('catalog.routes._tiff_to_jpeg_bytes', lambda asset_path: b'jpeg-bytes')
    client = TestClient(app)
    rv = client.get('/catalog/local/asset', params={'path': 'x'})
    assert rv.status_code == 200
    assert rv.headers.get('content-type', '').startswith('image/jpeg')
    assert rv.content == b'jpeg-bytes'


def test_erp_import_and_status(monkeypatch):
    target_path = os.path.join(os.getcwd(), 'reports', '_test_erp_products.json')
    if os.path.exists(target_path):
        os.remove(target_path)

    monkeypatch.setenv('CATALOG_ERP_JSON_PATH', target_path)

    client = TestClient(app)
    rv = client.post('/catalog/erp/import', json={
        'products': [
            {
                'codigo': '9911',
                'nome': 'Produto ERP',
                'categoria': 'LUMINARIA',
                'descricao': 'Descricao vinda do ERP',
                'voltagem': '220V',
            }
        ]
    })
    assert rv.status_code == 200
    payload = rv.json()
    assert payload['products_imported'] == 1

    status = client.get('/catalog/erp/status')
    assert status.status_code == 200
    data = status.json()
    assert data['exists'] is True
    assert data['products_loaded'] == 1
    assert data['last_change_summary']['added_count'] == 1
    assert data['last_change_summary']['updated_count'] == 0
    assert data['last_change_summary']['removed_count'] == 0
    assert data['last_change_summary']['unchanged_count'] == 0

    if os.path.exists(target_path):
        os.remove(target_path)


def test_photos_prefers_local(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.categorize_local_photos',
        lambda code: {'white_background': 'local1', 'ambient': None, 'measures': None}
    )
    monkeypatch.setattr('catalog.onedrive.list_shared_items', lambda shareUrl: (_ for _ in ()).throw(RuntimeError('should not call')))
    client = TestClient(app)
    rv = client.get('/catalog/photos', params={'shareUrl': 'x', 'code': 'ABC'})
    assert rv.status_code == 200
    assert rv.json()['white_background'] == 'local1'


def test_photos_local_mode_without_share_url(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.categorize_local_photos',
        lambda code: {'white_background': None, 'ambient': None, 'measures': None}
    )
    monkeypatch.setattr('catalog.onedrive.resolve_local_products_root', lambda: r'C:\Users\joao.silva\OneDrive\MARKETING\Catalogo')
    monkeypatch.setattr(
        'catalog.onedrive.list_shared_items',
        lambda shareUrl: (_ for _ in ()).throw(RuntimeError('should not call'))
    )
    client = TestClient(app)
    rv = client.get('/catalog/photos', params={'code': 'ABC'})
    assert rv.status_code == 200
    assert rv.json() == {'white_background': None, 'ambient': None, 'measures': None}


def test_erp_upload_raw_json(monkeypatch):
    target_path = os.path.join(os.getcwd(), 'reports', '_test_erp_upload_target.json')
    inbox_dir = os.path.join(os.getcwd(), 'reports', '_test_erp_inbox')

    if os.path.exists(target_path):
        os.remove(target_path)
    if os.path.isdir(inbox_dir):
        for entry in os.listdir(inbox_dir):
            os.remove(os.path.join(inbox_dir, entry))
        os.rmdir(inbox_dir)

    monkeypatch.setenv('CATALOG_ERP_JSON_PATH', target_path)
    monkeypatch.setenv('CATALOG_ERP_INBOX_DIR', inbox_dir)

    client = TestClient(app)
    body = (
        '{"products":[{"codigo":"8877","nome":"Produto Upload",'
        '"categoria":"PENDENTE","descricao":"Arquivo recebido"}]}'
    )
    rv = client.post(
        '/catalog/erp/upload',
        params={'filename': 'pcprodut_upload.json'},
        content=body.encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    assert rv.status_code == 200
    data = rv.json()
    assert data['products_imported'] == 1
    assert os.path.exists(data['uploaded_path'])
    assert data['source_name'] == 'pcprodut_upload.json'

    status = client.get('/catalog/erp/status')
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload['products_loaded'] == 1
    assert status_payload['source_name'] == 'pcprodut_upload.json'
    assert status_payload['source_path'].endswith('pcprodut_upload.json')

    if os.path.exists(target_path):
        os.remove(target_path)
    if os.path.isdir(inbox_dir):
        for entry in os.listdir(inbox_dir):
            os.remove(os.path.join(inbox_dir, entry))
        os.rmdir(inbox_dir)


def test_erp_upload_rejects_large_payload(monkeypatch):
    monkeypatch.setenv('CATALOG_ERP_MAX_UPLOAD_BYTES', '16')
    client = TestClient(app)
    rv = client.post(
        '/catalog/erp/upload',
        params={'filename': 'oversized.json'},
        content=b'{"products":[{"codigo":"8877"}]}',
        headers={'Content-Type': 'application/json'},
    )
    assert rv.status_code == 413
    assert rv.json()['error'] == 'ERP upload too large'


def test_erp_import_file_endpoint(monkeypatch):
    source_path = os.path.join(os.getcwd(), 'reports', '_test_erp_source.json')
    target_path = os.path.join(os.getcwd(), 'reports', '_test_erp_target_from_file.json')

    for path in (source_path, target_path):
        if os.path.exists(path):
            os.remove(path)

    with open(source_path, 'w', encoding='utf-8') as handle:
        handle.write(
            '{"products":[{"codigo":"7788","nome":"Produto Arquivo","categoria":"LUMINARIA"}]}'
        )

    monkeypatch.setenv('CATALOG_ERP_JSON_PATH', target_path)

    client = TestClient(app)
    rv = client.post('/catalog/erp/import-file', json={'file_path': 'reports/_test_erp_source.json'})
    assert rv.status_code == 200
    data = rv.json()
    assert data['products_imported'] == 1
    assert data['source_path'].endswith('_test_erp_source.json')
    assert data['source_name'] == '_test_erp_source.json'
    assert os.path.exists(target_path)

    status = client.get('/catalog/erp/status')
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload['source_path'].endswith('_test_erp_source.json')
    assert status_payload['source_name'] == '_test_erp_source.json'

    files = client.get('/catalog/erp/files')
    assert files.status_code == 200
    payload = files.json()
    assert 'files' in payload
    assert any(item['is_active'] for item in payload['files'])
    assert any(item['is_deployed_source'] for item in payload['files'] if item['name'] == '_test_erp_source.json')

    for path in (source_path, target_path):
        if os.path.exists(path):
            os.remove(path)


def test_erp_import_file_rejects_path_traversal():
    client = TestClient(app)
    rv = client.post('/catalog/erp/import-file', json={'file_path': '..\\app.py'})
    assert rv.status_code == 400
    assert 'error' in rv.json()


def test_erp_stage_file_and_preview(monkeypatch):
    target_path = os.path.join(os.getcwd(), 'reports', '_test_erp_stage_target.json')
    inbox_dir = os.path.join(os.getcwd(), 'reports', '_test_erp_stage_inbox')

    if os.path.exists(target_path):
        os.remove(target_path)
    if os.path.isdir(inbox_dir):
        for entry in os.listdir(inbox_dir):
            os.remove(os.path.join(inbox_dir, entry))
        os.rmdir(inbox_dir)

    monkeypatch.setenv('CATALOG_ERP_JSON_PATH', target_path)
    monkeypatch.setenv('CATALOG_ERP_INBOX_DIR', inbox_dir)

    client = TestClient(app)
    body = (
        '{"products":['
        '{"codigo":"1101","nome":"Produto Staged","categoria":"ARANDELA"},'
        '{"codigo":"1102","nome":"Produto Dois","categoria":"PAINEL"}'
        ']}'
    )
    rv = client.post(
        '/catalog/erp/stage-file',
        params={'filename': 'pcprodut_stage.json'},
        content=body.encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    assert rv.status_code == 200
    staged = rv.json()
    assert staged['staged'] is True
    assert staged['products_loaded'] == 2
    assert staged['name'] == 'pcprodut_stage.json'
    assert staged['is_active'] is False
    assert os.path.exists(staged['path'])

    preview = client.get('/catalog/erp/files/preview', params={'file_path': staged['path']})
    assert preview.status_code == 200
    payload = preview.json()
    assert payload['products_loaded'] == 2
    assert payload['records_detected'] == 2
    assert payload['ignored_records'] == 0
    assert payload['categories'][0]['count'] >= 1
    assert any(item['Codigo'] == '1101' for item in payload['sample_products'])
    assert payload['change_summary']['added_count'] == 2
    assert payload['change_summary']['updated_count'] == 0
    assert payload['change_summary']['removed_count'] == 0
    assert payload['change_summary']['unchanged_count'] == 0
    assert any(item['change_type'] == 'added' for item in payload['change_summary']['changes'])

    status = client.get('/catalog/erp/status')
    assert status.status_code == 200
    assert status.json()['products_loaded'] == 0

    if os.path.exists(target_path):
        os.remove(target_path)
    if os.path.isdir(inbox_dir):
        for entry in os.listdir(inbox_dir):
            os.remove(os.path.join(inbox_dir, entry))
        os.rmdir(inbox_dir)


def test_catalog_export_csv(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '9911',
                'Nome': 'Produto Exportavel',
                'Categoria': 'LUMINARIA',
                'Descricao': 'Descricao para exportacao',
                'CODAUXILIAR': '7890000000001',
            }
        ]
    )
    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'csv'})
    assert rv.status_code == 200
    assert rv.headers.get('content-type', '').startswith('text/csv')
    assert 'attachment; filename="catalogo-produtos-organizado.csv"' == rv.headers.get('content-disposition')
    payload = rv.content.decode('utf-8-sig')
    assert 'Codigo;Nome;Categoria' in payload
    assert '9911' in payload
    assert 'Produto Exportavel' in payload
    assert rv.headers['cache-control'] == 'private, no-cache'
    assert rv.headers['etag'].startswith('"')

    not_modified = client.get(
        '/catalog/export',
        params={'format': 'csv'},
        headers={'If-None-Match': rv.headers['etag']},
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b''


def test_catalog_export_csv_uses_excel_pt_br_columns(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '5966',
                'Nome': 'LAMPADA LED BULBO T100 50W 6500K',
                'Categoria': 'LAMPADA',
                'Descricao': 'Produto com vírgula, acento e 50W',
            }
        ],
    )

    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'csv', 'code': '5966'})
    payload = rv.content.decode('utf-8-sig')
    rows = list(csv.DictReader(StringIO(payload), delimiter=';'))

    assert payload.startswith('Codigo;Nome;Categoria;Descricao')
    assert '\r\n' in payload
    assert len(rows) == 1
    assert rows[0]['Codigo'] == '5966'
    assert rows[0]['Descricao'] == 'Produto com vírgula, acento e 50W'
    assert rv.headers.get('content-disposition') == 'attachment; filename="produto-5966-organizado.csv"'


def test_catalog_export_json_filters_brand(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {'Codigo': '9911', 'Nome': 'Produto Nitrolux', 'Categoria': 'LUMINARIA', 'CODMARCA': '1'},
            {'Codigo': '8822', 'Nome': 'Produto Pienza', 'Categoria': 'LUMINARIA', 'CODMARCA': '2'},
        ]
    )
    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'json', 'brand': 'pienza'})
    assert rv.status_code == 200
    assert 'attachment; filename="catalogo-pienza.json"' == rv.headers.get('content-disposition')
    payload = rv.json()
    assert len(payload['products']) == 1
    assert payload['products'][0]['Codigo'] == '8822'


def test_catalog_export_xlsx_single_product(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [{'Codigo': '9911', 'Nome': 'Produto Exportavel', 'Categoria': 'LUMINARIA'}]
    )
    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'xls', 'code': '9911'})
    assert rv.status_code == 200
    assert rv.headers.get('content-type', '').startswith(
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    assert rv.content[:4] == b'PK\x03\x04'


def test_catalog_export_pdf_single_product(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '9911',
                'Nome': 'Produto Exportavel',
                'Categoria': 'LUMINARIA',
                'Descricao': 'Descricao para exportacao',
                'Especificacoes': 'Potencia: 12W',
            }
        ]
    )
    monkeypatch.setattr('catalog.onedrive.find_local_images_for_code', lambda code: [])
    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'pdf', 'code': '9911'})
    assert rv.status_code == 200
    assert rv.headers.get('content-type', '').startswith('application/pdf')
    assert rv.content[:5] == b'%PDF-'


def test_catalog_export_technical_sheet_single_product(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '9911',
                'Nome': 'Luminaria Tecnica',
                'Categoria': 'LUMINARIA',
                'Descricao': 'Produto para ficha tecnica',
                'Especificacoes': 'Potencia: 12W | Tensao: Bivolt | Garantia: 2 anos',
            }
        ]
    )
    monkeypatch.setattr('catalog.onedrive.find_local_images_for_code', lambda code: [])

    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'ficha', 'code': '9911'})

    assert rv.status_code == 200
    assert rv.headers.get('content-type', '').startswith('application/pdf')
    assert 'attachment; filename="ficha-tecnica-9911-alta-resolucao-v2.pdf"' == rv.headers.get('content-disposition')
    assert rv.content[:5] == b'%PDF-'


def test_catalog_export_uses_catalog_media_enrichment(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [{'Codigo': '3009', 'Nome': 'Produto com foto', 'Categoria': 'PENDENTE'}],
    )
    monkeypatch.setattr(
        'catalog.cdn_media.enrich_products_with_photos',
        lambda products: [{**products[0], 'URLFoto': 'https://cdn.example/3009_1.jpg'}],
    )
    monkeypatch.setattr('catalog.vercel_blob_media.enrich_products_with_photos', lambda products: products)

    from catalog import exporter

    products = exporter._load_products()

    assert products[0]['URLFoto'] == 'https://cdn.example/3009_1.jpg'


def test_technical_sheet_deduplicates_equivalent_spec_labels():
    from catalog import exporter

    specs = 'Potencia: 45W | POTENCIA(W): 45W | Tensao: Bivolt | TENSAO(V): Bivolt'
    rows = exporter._technical_sheet_rows({}, specs)
    enriched_rows = list(rows)
    seen = {exporter._canonical_spec_key(label) for label, _ in enriched_rows}
    for label, value in exporter._parse_specs_pairs(specs):
        key = exporter._canonical_spec_key(label)
        if key not in seen:
            enriched_rows.append((label, value))
            seen.add(key)

    assert [exporter._canonical_spec_key(label) for label, _ in enriched_rows].count('potencia') == 1
    assert [exporter._canonical_spec_key(label) for label, _ in enriched_rows].count('tensao') == 1


def test_pdf_uses_bundled_font():
    from catalog import exporter

    regular = exporter._load_font(20)
    bold = exporter._load_font(20, bold=True)

    assert exporter.BUNDLED_FONT_PATH.is_file()
    assert 'Noto Sans' in regular.getname()[0]
    assert bold.getname()[1] == 'Bold'


def test_catalog_export_technical_sheet_requires_code(monkeypatch):
    monkeypatch.setattr('catalog.onedrive.list_local_products', lambda: [{'Codigo': '9911'}])

    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'ficha'})

    assert rv.status_code == 400
    assert 'technical sheet export requires a product code' in rv.json()['error']


def test_catalog_export_zip_includes_photos(monkeypatch):
    photo_path = os.path.join(os.getcwd(), 'reports', '_test_export_photo.jpg')
    if os.path.exists(photo_path):
        os.remove(photo_path)
    with open(photo_path, 'wb') as handle:
        handle.write(b'fake-image-bytes')

    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '9911',
                'Nome': 'Produto Exportavel',
                'Categoria': 'LUMINARIA',
                'FotoBranco': '/catalog/local/asset?path=9911_1.jpg',
            }
        ]
    )
    monkeypatch.setattr('catalog.onedrive.find_local_images_for_code', lambda code: [])
    monkeypatch.setattr('catalog.onedrive.resolve_local_asset_path', lambda rel_path: photo_path)

    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'zip', 'code': '9911'})
    assert rv.status_code == 200
    assert rv.headers.get('content-type', '').startswith('application/zip')

    with ZipFile(BytesIO(rv.content)) as archive:
        names = archive.namelist()
        assert 'produto-9911.csv' in names
        assert 'produto-9911.json' in names
        assert 'manifesto_fotos.csv' in names
        assert any(name.startswith('fotos/9911/') and name.endswith('.jpg') for name in names)

    if os.path.exists(photo_path):
        os.remove(photo_path)


def test_catalog_export_zip_blocks_private_remote_photo_urls(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: [
            {
                'Codigo': '9911',
                'Nome': 'Produto Exportavel',
                'Categoria': 'LUMINARIA',
                'FotoBranco': 'http://127.0.0.1/private.jpg',
            }
        ]
    )
    monkeypatch.setattr('catalog.onedrive.find_local_images_for_code', lambda code: [])

    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'zip', 'code': '9911'})
    assert rv.status_code == 200

    with ZipFile(BytesIO(rv.content)) as archive:
        names = archive.namelist()
        assert not any(name.startswith('fotos/9911/') for name in names)
        manifest = archive.read('manifesto_fotos.csv').decode('utf-8-sig')
        assert 'http://127.0.0.1/private.jpg' in manifest


def test_catalog_export_rejects_invalid_format(monkeypatch):
    monkeypatch.setattr('catalog.onedrive.list_local_products', lambda: [{'Codigo': '9911'}])
    client = TestClient(app)
    rv = client.get('/catalog/export', params={'format': 'xml'})
    assert rv.status_code == 400
    assert 'error' in rv.json()


def test_internal_errors_are_sanitized(monkeypatch):
    monkeypatch.setattr(
        'catalog.onedrive.list_local_products',
        lambda: (_ for _ in ()).throw(RuntimeError('secret path D:\\catalogo\\sensitive.txt'))
    )
    client = TestClient(app)
    rv = client.get('/catalog/local/produtos')
    assert rv.status_code == 500
    assert rv.json() == {'error': 'internal server error'}
