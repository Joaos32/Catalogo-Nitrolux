"""Conditional private Blob writes until the Python SDK exposes if_match.

The wire contract follows Vercel's official @vercel/blob put-helpers.ts:
https://github.com/vercel/storage/blob/main/packages/blob/src/put-helpers.ts
Never replace a failed conditional write with an unconditional overwrite.
"""

import requests


class BlobWriteConflictError(ValueError):
    pass


def put_versioned(path: str, content: bytes, *, token: str,
                  expected_etag: str | None, expected_missing: bool) -> str:
    if not expected_missing and not expected_etag:
        raise BlobWriteConflictError("Stored data changed; reload and retry")
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-version": "13",
        "x-vercel-blob-access": "private",
        "x-content-type": "application/json; charset=utf-8",
        "x-add-random-suffix": "0",
        "x-allow-overwrite": "0" if expected_missing else "1",
        "x-cache-control-max-age": "0",
    }
    if not expected_missing:
        headers["x-if-match"] = expected_etag
    # No automatic retries: a timeout can mean the write already committed.
    response = requests.put(
        "https://vercel.com/api/blob", params={"pathname": path},
        data=content, headers=headers, timeout=(5, 20), allow_redirects=False,
    )
    try:
        result = response.json()
        error = result.get("error") or {}
        if response.status_code in {409, 412} or error.get("code") == "precondition_failed":
            raise BlobWriteConflictError("Stored data changed; reload and retry")
        # Existing-path creation may be reported as bad_request by Blob.
        if error:
            if expected_missing and "already exists" in str(error.get("message", "")).lower():
                raise BlobWriteConflictError("Stored data already exists; reload and retry")
            response.raise_for_status()
            raise RuntimeError("Private storage rejected the write")
        response.raise_for_status()
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Private storage returned an unexpected response")
        etag = result.get("etag")
        if not isinstance(etag, str) or not etag:
            raise RuntimeError("Private storage did not return a version; reload before retrying")
        return etag
    finally:
        response.close()
