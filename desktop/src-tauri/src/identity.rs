//! Validación de IDENTIDAD de backend y frontend antes de adoptar o navegar.
//!
//! Lección real (2026-07-10, máquina del fundador): "responde en el puerto"
//! no es "es MIA". En el 8000 estaba voicebox-server.exe (una app ajena que
//! responde 200 a /health) y en el 3100 el Next.js de OTRO proyecto
//! ("Intelligence Sura"); la cáscara adoptó ambos y navegó a la app
//! equivocada. La colisión de puertos es un caso ESPERADO, no excepcional.
//!
//! Señales de identidad elegidas (baratas, sin dependencia nueva):
//!
//! - **Backend**: el JSON de `/health` de MIA siempre trae las claves
//!   `"db"`, `"pgvector"` y `"embed_model"` — incluso en estado degradado
//!   (ver `backend/mia/api/main.py::health`). Un health ajeno que responda
//!   200 casi nunca traerá esa combinación.
//! - **Frontend**: `frontend/next.config.mjs` fija en TODAS las rutas
//!   (`/:path*`) la huella de cabeceras `X-Frame-Options: DENY` +
//!   `Content-Security-Policy: frame-ancestors 'none'` +
//!   `Permissions-Policy: camera=()...`. Esa combinación exacta es muy
//!   improbable en una app ajena, y además está protegida por contrato: el
//!   gate `execution/test_frontend_packaging.py` falla si alguien quita esas
//!   cabeceras de next.config.mjs (la señal no se puede romper en silencio).
//!   Se prefirió la huella de cabeceras sobre un marcador en el HTML (p.ej.
//!   el `<title>`) porque las cabeceras aplican a todas las rutas —incluso
//!   redirecciones— y tienen gate propio; el título puede cambiar por página
//!   sin que ningún test lo note.
//!
//! Las tres respuestas posibles se separan a propósito:
//! `Mia` (identidad confirmada), `NotMia` (responde pero es OTRO programa —
//! fallar YA, reintentarlo es inútil) y `NoResponse` (aún no responde —
//! reintentar dentro del deadline).

use std::time::Duration;

/// Resultado de un sondeo de identidad.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Identity {
    /// Responde y las señales confirman que es MIA.
    Mia,
    /// Responde, pero NO es MIA (otro programa ocupa el puerto).
    NotMia,
    /// No responde (apagado, arrancando o error de red) — reintentar.
    NoResponse,
}

/// Backend: GET a `health_url` y exigir el JSON propio de MIA.
/// 2xx + JSON con claves "db", "pgvector" y "embed_model" → Mia.
/// 2xx sin esas claves (o cuerpo no-JSON) → NotMia. Resto → NoResponse.
pub async fn backend_identity(client: &reqwest::Client, health_url: &str) -> Identity {
    let resp = match client
        .get(health_url)
        .timeout(Duration::from_secs(4))
        .send()
        .await
    {
        Ok(r) => r,
        Err(_) => return Identity::NoResponse,
    };
    if !resp.status().is_success() {
        return Identity::NoResponse;
    }
    let body = match resp.text().await {
        Ok(b) => b,
        Err(_) => return Identity::NoResponse,
    };
    match serde_json::from_str::<serde_json::Value>(&body) {
        Ok(json) => {
            let o = json.as_object();
            let has = |k: &str| o.map(|m| m.contains_key(k)).unwrap_or(false);
            if has("db") && has("pgvector") && has("embed_model") {
                Identity::Mia
            } else {
                Identity::NotMia
            }
        }
        Err(_) => Identity::NotMia,
    }
}

/// Frontend: GET a `url` y exigir la huella de cabeceras que
/// `frontend/next.config.mjs` fija en todas las rutas de MIA.
pub async fn frontend_identity(client: &reqwest::Client, url: &str) -> Identity {
    let resp = match client.get(url).timeout(Duration::from_secs(4)).send().await {
        Ok(r) => r,
        Err(_) => return Identity::NoResponse,
    };
    if !resp.status().is_success() {
        return Identity::NoResponse;
    }
    let header = |name: &str| -> String {
        resp.headers()
            .get(name)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_ascii_lowercase()
    };
    let xfo_deny = header("x-frame-options") == "deny";
    let csp_no_frames = header("content-security-policy").contains("frame-ancestors 'none'");
    let perm_policy = header("permissions-policy").contains("camera=()");
    if xfo_deny && csp_no_frames && perm_policy {
        Identity::Mia
    } else {
        Identity::NotMia
    }
}
