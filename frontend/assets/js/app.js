/**
 * app.js — Cliente fetch padronizado para APIs do projeto
 *
 * Funcionalidades:
 *   - Retry automático em 429 (too many requests) e 503 (serviço indisponível)
 *   - Backoff exponencial com jitter para evitar thundering herd
 *   - Renovação automática de token JWT (401 → refresh → retry)
 *   - Timeout configurável por request
 *   - Logs estruturados (desabilitados em produção)
 *
 * Uso básico:
 *   import { apiFetch } from '/assets/js/app.js';
 *
 *   const data = await apiFetch('/api/user/profile');
 *   await apiFetch('/api/register', { method: 'POST', body: JSON.stringify(payload) });
 *
 * Configuração:
 *   Defina window.APP_CONFIG antes de importar este módulo:
 *   <script>
 *     window.APP_CONFIG = {
 *       apiBase: 'https://func-meu-projeto.azurewebsites.net',
 *       tokenKey: 'access_token',
 *       refreshTokenKey: 'refresh_token',
 *     };
 *   </script>
 */

// ---------------------------------------------------------------------------
// Configuração padrão — sobrescrita via window.APP_CONFIG
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG = {
  apiBase: '',                    // Base URL da API (sem trailing slash)
  tokenKey: 'access_token',       // localStorage key do access token
  refreshTokenKey: 'refresh_token', // localStorage key do refresh token
  refreshEndpoint: '/api/auth/refresh', // Endpoint para renovar o token
  timeoutMs: 30_000,              // Timeout padrão em ms
  maxRetries: 3,                  // Tentativas máximas (429/503)
  initialRetryDelayMs: 500,       // Delay inicial do backoff
  debug: false,                   // Logs detalhados
};

function getConfig() {
  return { ...DEFAULT_CONFIG, ...(window.APP_CONFIG || {}) };
}

// ---------------------------------------------------------------------------
// Helpers internos
// ---------------------------------------------------------------------------

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/** Backoff exponencial com jitter: delay = base * 2^tentativa + random(0..100ms) */
function retryDelay(attempt, baseMs) {
  const exp = Math.min(baseMs * Math.pow(2, attempt), 30_000); // máx 30s
  const jitter = Math.random() * 100;
  return exp + jitter;
}

function log(...args) {
  if (getConfig().debug) console.debug('[apiFetch]', ...args);
}

/** Retorna o access token armazenado no localStorage. */
function getToken() {
  return localStorage.getItem(getConfig().tokenKey) || '';
}

/** Armazena access e refresh tokens após login/refresh bem-sucedido. */
export function saveTokens({ access_token, refresh_token }) {
  const cfg = getConfig();
  if (access_token) localStorage.setItem(cfg.tokenKey, access_token);
  if (refresh_token) localStorage.setItem(cfg.refreshTokenKey, refresh_token);
}

/** Remove tokens do localStorage (logout). */
export function clearTokens() {
  const cfg = getConfig();
  localStorage.removeItem(cfg.tokenKey);
  localStorage.removeItem(cfg.refreshTokenKey);
}

// ---------------------------------------------------------------------------
// Renovação de token JWT
// ---------------------------------------------------------------------------

let _refreshPromise = null; // evita múltiplas chamadas simultâneas de refresh

async function refreshAccessToken() {
  if (_refreshPromise) return _refreshPromise; // deduplica chamadas paralelas

  const cfg = getConfig();
  const refreshToken = localStorage.getItem(cfg.refreshTokenKey);
  if (!refreshToken) throw new Error('Sem refresh token — usuário deve fazer login novamente.');

  _refreshPromise = (async () => {
    const res = await fetch(`${cfg.apiBase}${cfg.refreshEndpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      clearTokens();
      throw new Error(`Refresh falhou (${res.status}) — sessão expirada.`);
    }

    const data = await res.json();
    saveTokens(data);
    log('Token renovado com sucesso.');
    return data.access_token;
  })().finally(() => { _refreshPromise = null; });

  return _refreshPromise;
}

// ---------------------------------------------------------------------------
// apiFetch — função principal
// ---------------------------------------------------------------------------

/**
 * Faz uma requisição autenticada para a API com retry e renovação de token.
 *
 * @param {string} path - Caminho relativo (ex: '/api/user/profile') ou URL absoluta
 * @param {RequestInit} options - Opções do fetch (method, body, headers, etc.)
 * @param {object} extras - Opções extras: { retry: bool, timeoutMs: number }
 * @returns {Promise<any>} - Resultado parseado como JSON
 * @throws {ApiError} - Com status e message estruturados
 */
export async function apiFetch(path, options = {}, extras = {}) {
  const cfg = getConfig();
  const url = path.startsWith('http') ? path : `${cfg.apiBase}${path}`;
  const timeoutMs = extras.timeoutMs ?? cfg.timeoutMs;
  const shouldRetry = extras.retry !== false;
  const maxRetries = shouldRetry ? cfg.maxRetries : 0;

  // Headers padrão
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...options.headers,
  };

  // Injeta token se existir
  const token = getToken();
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let attempt = 0;
  let lastError = null;

  while (attempt <= maxRetries) {
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      log(`${options.method || 'GET'} ${url} (tentativa ${attempt + 1}/${maxRetries + 1})`);

      const res = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timerId);

      // 401 → tenta renovar token uma vez
      if (res.status === 401 && attempt === 0 && token) {
        log('401 recebido — tentando renovar token...');
        try {
          const newToken = await refreshAccessToken();
          headers['Authorization'] = `Bearer ${newToken}`;
          attempt++;
          continue;
        } catch (refreshError) {
          // Refresh falhou — redireciona para login
          window.dispatchEvent(new CustomEvent('session:expired', { detail: refreshError }));
          throw refreshError;
        }
      }

      // 429 / 503 → retry com backoff
      if ((res.status === 429 || res.status === 503) && attempt < maxRetries) {
        const retryAfter = parseInt(res.headers.get('Retry-After') || '0', 10);
        const delay = retryAfter > 0
          ? retryAfter * 1000
          : retryDelay(attempt, cfg.initialRetryDelayMs);
        log(`${res.status} — aguardando ${Math.round(delay)}ms antes de retry...`);
        await sleep(delay);
        attempt++;
        continue;
      }

      // Resposta bem-sucedida
      if (res.ok) {
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          return await res.json();
        }
        return await res.text();
      }

      // Erro HTTP tratado
      let errorBody = {};
      try { errorBody = await res.json(); } catch { /* ignore */ }
      throw new ApiError(res.status, errorBody.message || res.statusText, errorBody);

    } catch (err) {
      clearTimeout(timerId);

      if (err instanceof ApiError) throw err;

      if (err.name === 'AbortError') {
        throw new ApiError(0, `Timeout após ${timeoutMs}ms: ${url}`);
      }

      // Erro de rede (sem resposta) — tenta novamente se possível
      lastError = err;
      if (attempt < maxRetries) {
        const delay = retryDelay(attempt, cfg.initialRetryDelayMs);
        log(`Erro de rede — retry em ${Math.round(delay)}ms: ${err.message}`);
        await sleep(delay);
        attempt++;
        continue;
      }

      throw new ApiError(0, `Erro de rede: ${err.message}`);
    }
  }

  throw lastError || new ApiError(0, `Falha após ${maxRetries} tentativas: ${url}`);
}

// ---------------------------------------------------------------------------
// ApiError — erro estruturado para facilitar handling no UI
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  /**
   * @param {number} status - Código HTTP (0 = erro de rede/timeout)
   * @param {string} message - Mensagem legível
   * @param {object} body - Body completo do response de erro
   */
  constructor(status, message, body = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }

  /** Retorna true para erros esperados que o UI deve mostrar ao usuário. */
  get isUserFacing() {
    return this.status >= 400 && this.status < 500;
  }

  /** Retorna true para erros de servidor que devem ser logados. */
  get isServerError() {
    return this.status >= 500 || this.status === 0;
  }
}

// ---------------------------------------------------------------------------
// Helpers de alto nível
// ---------------------------------------------------------------------------

/** POST com JSON. */
export function apiPost(path, data, extras = {}) {
  return apiFetch(path, {
    method: 'POST',
    body: JSON.stringify(data),
  }, extras);
}

/** PUT com JSON. */
export function apiPut(path, data, extras = {}) {
  return apiFetch(path, {
    method: 'PUT',
    body: JSON.stringify(data),
  }, extras);
}

/** DELETE. */
export function apiDelete(path, extras = {}) {
  return apiFetch(path, { method: 'DELETE' }, extras);
}
