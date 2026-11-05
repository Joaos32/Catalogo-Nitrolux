import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

export function useUnsavedChanges(dirty: boolean): void {
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Há alterações não salvas. Sair e descartar essas alterações?"))
      blocker.proceed();
    else blocker.reset();
  }, [blocker]);
}
