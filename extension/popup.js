// Extension popup logic.
//
// Since the backend can serve multiple independent accounts, the popup
// has three possible states, and shows only the one that applies based on
// what's already stored in chrome.storage.local:
//   1. seccionBackend: no backend URL configured yet.
//   2. seccionLogin: backend known, but no active session.
//   3. seccionPrincipal: backend + session ready — the main send button.
//
// Sending an offer does not do the actual work here — it only notifies
// background.js (the service worker) to start, and returns immediately.
// The popup is torn down as soon as it loses focus or the tab changes,
// which would cancel any request in flight; the service worker stays
// alive and reports the result via a system notification.

const seccionBackend = document.getElementById("seccionBackend");
const seccionLogin = document.getElementById("seccionLogin");
const seccionPrincipal = document.getElementById("seccionPrincipal");
const estado = document.getElementById("estado");

function mostrarSeccion(seccion) {
  for (const s of [seccionBackend, seccionLogin, seccionPrincipal]) {
    s.hidden = s !== seccion;
  }
  estado.textContent = "";
  estado.className = "";
}

function mostrarError(mensaje) {
  estado.textContent = mensaje;
  estado.className = "error";
}

// Strips a trailing slash ("https://x.com/" -> "https://x.com") to avoid
// building URLs with a duplicated "//" later on.
function normalizarUrl(url) {
  return url.trim().replace(/\/+$/, "");
}

async function iniciar() {
  const { backendUrl, token } = await chrome.storage.local.get(["backendUrl", "token"]);

  if (!backendUrl) {
    mostrarSeccion(seccionBackend);
    return;
  }
  if (!token) {
    mostrarSeccion(seccionLogin);
    return;
  }

  const { email } = await chrome.storage.local.get("email");
  document.getElementById("sesionInfo").textContent = email ? `Sesión: ${email}` : "";
  document.getElementById("enlacePanel").href = `${backendUrl}/panel`;
  mostrarSeccion(seccionPrincipal);
}

// --- Step 1: save the backend URL ----------------------------------------

document.getElementById("btnGuardarBackend").addEventListener("click", async () => {
  const boton = document.getElementById("btnGuardarBackend");
  const urlEscrita = document.getElementById("campoBackend").value;
  if (!urlEscrita) {
    mostrarError("Escribe la URL del backend.");
    return;
  }

  const url = normalizarUrl(urlEscrita);
  if (!/^https?:\/\/.+/.test(url)) {
    mostrarError("La URL debe empezar por http:// o https://");
    return;
  }

  boton.disabled = true;
  try {
    // Manifest V3 requires explicit host permission before the extension
    // can talk to a given origin. Since the backend URL is user-provided
    // rather than fixed in the manifest, permission is requested at this
    // point, scoped only to that origin (not a blanket "all sites" grant).
    const concedido = await chrome.permissions.request({ origins: [`${url}/*`] });
    if (!concedido) {
      mostrarError("Sin ese permiso la extensión no puede hablar con el backend.");
      return;
    }

    await chrome.storage.local.set({ backendUrl: url });
    mostrarSeccion(seccionLogin);
  } catch (error) {
    mostrarError(`No se pudo guardar: ${error.message}`);
  } finally {
    boton.disabled = false;
  }
});

// --- Step 2: login ---------------------------------------------------------

document.getElementById("btnLogin").addEventListener("click", async () => {
  const boton = document.getElementById("btnLogin");
  const email = document.getElementById("campoEmail").value;
  const password = document.getElementById("campoPassword").value;
  if (!email || !password) {
    mostrarError("Rellena email y contraseña.");
    return;
  }

  const { backendUrl } = await chrome.storage.local.get("backendUrl");
  boton.disabled = true;
  boton.textContent = "Entrando…";
  try {
    const respuestaLogin = await fetch(`${backendUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!respuestaLogin.ok) {
      const error = await respuestaLogin.json().catch(() => null);
      mostrarError(error?.detail || "No se pudo iniciar sesión.");
      return;
    }

    const { access_token } = await respuestaLogin.json();

    // The login response doesn't include the email, so it's fetched
    // separately with the new token to display "Sesión: user@..." without
    // decoding the JWT client-side.
    const respuestaYo = await fetch(`${backendUrl}/auth/yo`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const emailConfirmado = respuestaYo.ok ? (await respuestaYo.json()).email : email;

    await chrome.storage.local.set({ token: access_token, email: emailConfirmado });
    document.getElementById("campoPassword").value = "";
    await iniciar();
  } catch (error) {
    mostrarError(`No se pudo conectar con el backend: ${error.message}`);
  } finally {
    boton.disabled = false;
    boton.textContent = "Entrar";
  }
});

document.getElementById("btnCambiarBackendDesdeLogin").addEventListener("click", async () => {
  const { backendUrl } = await chrome.storage.local.get("backendUrl");
  await chrome.storage.local.remove(["backendUrl", "token", "email"]);
  document.getElementById("campoBackend").value = backendUrl || "";
  mostrarSeccion(seccionBackend);
});

// --- Step 3: authenticated -------------------------------------------------

document.getElementById("btnCerrarSesion").addEventListener("click", async () => {
  await chrome.storage.local.remove(["token", "email"]);
  mostrarSeccion(seccionLogin);
});

document.getElementById("enviar").addEventListener("click", () => {
  const boton = document.getElementById("enviar");
  chrome.runtime.sendMessage({ tipo: "ENVIAR_OFERTA" });

  estado.textContent = "Enviado — ya puedes cerrar esto. Una notificación avisará cuando termine.";
  estado.className = "ok";
  boton.disabled = true;
});

iniciar();
