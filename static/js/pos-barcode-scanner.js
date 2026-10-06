(() => {
  "use strict";

  const app = document.getElementById("pos-app");
  const dialog = document.getElementById("barcode-scanner-dialog");
  const video = document.getElementById("barcode-scanner-video");
  const status = document.getElementById("barcode-scanner-status");
  if (!app || !dialog || !video || !status) return;

  let reader = null;
  let controls = null;
  let starting = false;
  let detected = false;

  function setStatus(message, error = false) {
    status.textContent = message;
    status.classList.toggle("is-error", error);
  }

  function stopScanner() {
    controls?.stop?.();
    controls = null;
    const stream = video.srcObject;
    if (stream?.getTracks) stream.getTracks().forEach((track) => track.stop());
    video.pause();
    video.srcObject = null;
    reader?.reset?.();
    reader = null;
    starting = false;
  }

  function cameraErrorMessage(error) {
    if (!window.isSecureContext) return "La cámara requiere HTTPS o localhost.";
    if (error?.name === "NotAllowedError") return "Permiso de cámara denegado. Habilítelo en la configuración del navegador.";
    if (error?.name === "NotFoundError") return "No se encontró una cámara disponible.";
    if (error?.name === "NotReadableError") return "La cámara está siendo utilizada por otra aplicación.";
    return "No se pudo iniciar la cámara. Puede escribir el código en el buscador.";
  }

  function useBarcode(value, targetInput) {
    const barcode = String(value || "").trim();
    if (!barcode || detected) return;
    detected = true;
    navigator.vibrate?.(80);
    stopScanner();
    if (dialog.open) dialog.close();
    targetInput.value = barcode;
    targetInput.dispatchEvent(new CustomEvent("pos:barcode-detected", {
      bubbles: true,
      detail: { barcode },
    }));
    targetInput.focus();
  }

  async function startScanner(targetInput) {
    if (starting || controls) return;
    starting = true;
    detected = false;
    setStatus("Solicitando acceso a la cámara…");
    if (!dialog.open) dialog.showModal();
    try {
      reader = new window.ZXingBrowser.BrowserMultiFormatReader(undefined, {
        delayBetweenScanAttempts: 120,
        delayBetweenScanSuccess: 500,
      });
      controls = await reader.decodeFromConstraints(
        {
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        },
        video,
        (result) => {
          if (result) useBarcode(result.getText(), targetInput);
        },
      );
      starting = false;
      setStatus("Buscando código…");
    } catch (error) {
      stopScanner();
      setStatus(cameraErrorMessage(error), true);
    }
  }

  app.addEventListener("pos:scan-requested", (event) => {
    if (!window.ZXingBrowser?.BrowserMultiFormatReader || !navigator.mediaDevices?.getUserMedia) return;
    event.preventDefault();
    startScanner(event.detail.targetInput);
  });

  dialog.addEventListener("close", stopScanner);
  dialog.addEventListener("cancel", stopScanner);
  window.addEventListener("pagehide", stopScanner);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && dialog.open) dialog.close();
  });
})();
