// Extension service worker (Manifest V3).
//
// The popup (popup.html/popup.js) is torn down as soon as it loses focus
// or the tab changes, cancelling any in-flight fetch() along with it. The
// service worker stays alive independently of whether the popup is open,
// so the actual work (reading the page, calling the backend) happens
// here — the popup can be closed immediately after clicking, and a system
// notification reports the result when it's ready.
//
// The backend URL and session token are read from chrome.storage.local
// (set by popup.js) at the start of each send, rather than cached in a
// module-level variable, since either can change between sends.

chrome.runtime.onMessage.addListener((mensaje) => {
  if (mensaje.tipo === "ENVIAR_OFERTA") {
    enviarOfertaActiva();
  }
});

// --- Keep the service worker alive for the duration of a send ------------
//
// Manifest V3 service workers are suspended after ~30s of inactivity. A
// backend call here can legitimately take longer than that (automatic
// retries on a 503 from Gemini alone can add up to 15s), so a trivial
// Chrome API call is issued every 20s while a send is in progress to
// count as activity and prevent suspension; it stops as soon as the send
// finishes, successfully or not.
let intervaloDespertador = null;

function mantenerDespiertoMientrasDure() {
  intervaloDespertador = setInterval(() => chrome.runtime.getPlatformInfo(() => {}), 20_000);
}

function dejarDeMantenerDespierto() {
  clearInterval(intervaloDespertador);
  intervaloDespertador = null;
}

async function enviarOfertaActiva() {
  mantenerDespiertoMientrasDure();
  console.log("[JobTrack AI] Empezando a procesar la oferta de la pestaña activa...");

  try {
    const { backendUrl, token } = await chrome.storage.local.get(["backendUrl", "token"]);
    if (!backendUrl || !token) {
      throw new Error("El backend o la sesión todavía no están configurados — hazlo desde el icono de la extensión.");
    }

    const [pestana] = await chrome.tabs.query({ active: true, currentWindow: true });
    console.log("[JobTrack AI] Pestaña activa:", pestana?.url);

    if (!pestana?.id || !pestana.url?.startsWith("http")) {
      throw new Error("La pestaña activa no es una página web normal.");
    }

    const [{ result: textoPagina }] = await chrome.scripting.executeScript({
      target: { tabId: pestana.id },
      func: () => document.body.innerText,
    });
    console.log("[JobTrack AI] Texto de la página leído, longitud:", textoPagina?.length);

    console.log("[JobTrack AI] Llamando al backend (puede tardar si Gemini está saturado)...");
    const respuesta = await fetch(`${backendUrl}/candidaturas/extraer`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ url: pestana.url, contenido_pagina: textoPagina }),
    });
    console.log("[JobTrack AI] Respuesta del backend, status:", respuesta.status);

    if (respuesta.status === 401) {
      // Session expired or token no longer valid: clear the stored token
      // so the next popup open prompts for login again.
      await chrome.storage.local.remove(["token", "email"]);
      throw new Error("La sesión ha caducado — abre el icono de la extensión para iniciar sesión de nuevo.");
    }

    if (!respuesta.ok) {
      const cuerpoError = await respuesta.json().catch(() => null);
      throw new Error(cuerpoError?.detail || `Error del servidor (${respuesta.status})`);
    }

    const candidatura = await respuesta.json();
    mostrarNotificacion("Oferta guardada en JobTrack AI", `${candidatura.empresa} — ${candidatura.puesto}`);
  } catch (error) {
    console.error("[JobTrack AI] Error al procesar la oferta:", error);
    mostrarNotificacion("No se pudo guardar la oferta", error.message);
  } finally {
    dejarDeMantenerDespierto();
  }
}

function mostrarNotificacion(titulo, mensaje) {
  chrome.notifications.create(
    {
      type: "basic",
      iconUrl: "icon128.png",
      title: titulo,
      message: mensaje,
    },
    () => {
      // Chrome reports errors from callback-based APIs like this one via
      // chrome.runtime.lastError rather than throwing.
      if (chrome.runtime.lastError) {
        console.error("[JobTrack AI] No se pudo mostrar la notificación:", chrome.runtime.lastError.message);
      } else {
        console.log("[JobTrack AI] Notificación mostrada:", titulo);
      }
    }
  );
}
