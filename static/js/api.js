import { state } from './state.js';

export async function api(method, path, body = null) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(state.token ? { 'X-Token': state.token } : {}),
    },
  };
  if (body) opts.body = JSON.stringify(body);

  let res, data;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new Error('Réseau : ' + e.message);
  }
  try {
    data = await res.json();
  } catch (e) {
    throw new Error('Réponse non-JSON (HTTP ' + res.status + ')');
  }
  if (!res.ok) {
    const msg = data?.detail
      ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
      : 'HTTP ' + res.status;
    throw new Error(msg);
  }
  return data;
}
