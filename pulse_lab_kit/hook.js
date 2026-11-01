(function(){
if (location.host !== 'pulse.mirea.ru') return 'skip';
// v2 (с сервера, pulse_lab_kit/hook.js): встаёт поверх встроенного в приложение
if (window.__capy && window.__capy.v === 2) return 'ok';
var C = window.__capy = {v: 2, calls: [], n: 0, total: 0, pages: [], seen: {}};
var MAX_CALLS = 800, MAX_BODY = 3000000, MAX_TOTAL = 25000000;
var AUTHY = /\/\/(sso|auth|login|id|lk)\.|oauth|openid|oidc|\/token(\b|\?)|\/login(\b|\?)/i;
var SECRET = /authorization|cookie|token|session|secret|password|passwd|key/i;
var STATIC = /\.(js|mjs|css|png|jpe?g|gif|svg|webp|woff2?|ttf|ico|map)(\?|$)/i;
function jwtShape(t){
  try { var p = t.split('.')[1]; p = p.replace(/-/g,'+').replace(/_/g,'/'); while (p.length % 4) p += '=';
    var c = JSON.parse(decodeURIComponent(escape(atob(p)))); var o = {};
    ['exp','iat','nbf','auth_time','iss','aud','azp','typ','scope'].forEach(function(k){ if (k in c) o[k] = c[k]; });
    if (c.exp && c.iat) o.lifetime_min = Math.round((c.exp - c.iat) / 6) / 10;
    return o; } catch (e) { return 'не разобран'; }
}
function redact(v){
  v = String(v); var o = {redacted: true, len: v.length, scheme: v.indexOf(' ') > 0 ? v.split(' ')[0] : ''};
  var m = v.match(/[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/); if (m) o.jwt = jwtShape(m[0]);
  return o;
}
C.redact = redact;
function shapeJson(v, depth){
  if (v === null || typeof v === 'number' || typeof v === 'boolean') return v;
  if (typeof v === 'string') return (v.length > 40 || /[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/.test(v)) ? redact(v) : v;
  if (depth > 4) return '…';
  if (Array.isArray(v)) return v.slice(0, 5).map(function(x){ return shapeJson(x, depth + 1); });
  var o = {}; Object.keys(v).slice(0, 40).forEach(function(k){ o[k] = SECRET.test(k) && typeof v[k] === 'string' ? redact(v[k]) : shapeJson(v[k], depth + 1); });
  return o;
}
C.shape = function(s){ try { return shapeJson(JSON.parse(s), 0); } catch (e) { return (s && s.length > 40) ? redact(s) : s; } };
function hdr(name, v){ name = String(name).toLowerCase(); return [name, SECRET.test(name) ? redact(v) : String(v).slice(0, 300)]; }
function b64(buf){
  var a = new Uint8Array(buf), n = Math.min(a.length, MAX_BODY), s = '';
  for (var i = 0; i < n; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, Math.min(n, i + 0x8000)));
  C.total += n; return btoa(s);
}
function bodyOf(b){
  if (b == null) return null;
  if (typeof b === 'string') return b64(new TextEncoder().encode(b));
  if (b instanceof ArrayBuffer) return b64(b);
  if (ArrayBuffer.isView(b)) return b64(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
  return '(' + Object.prototype.toString.call(b) + ')';
}
function wanted(url){ return !STATIC.test(url) && C.n < MAX_CALLS; }
function keep(rec){ C.n++; C.calls.push(rec); }
var of = window.fetch;
if (of) window.fetch = function(input, init){
  var url = String((input && input.url) || input), t0 = Date.now();
  if (!wanted(url)) return of.apply(this, arguments);
  var rec = {kind: 'fetch', t: t0, page: location.pathname, url: url,
    method: (init && init.method) || (input && input.method) || 'GET', req_headers: {}};
  try {
    var h = new Headers((init && init.headers) || (input && input.headers) || {});
    h.forEach(function(v, k){ var p = hdr(k, v); rec.req_headers[p[0]] = p[1]; });
    if (!AUTHY.test(url) && init && init.body != null) rec.req = bodyOf(init.body);
  } catch (e) { rec.note = 'req: ' + e; }
  keep(rec);
  return of.apply(this, arguments).then(function(r){
    rec.status = r.status; rec.ms = Date.now() - t0; rec.resp_headers = {};
    r.headers.forEach(function(v, k){ var p = hdr(k, v); rec.resp_headers[p[0]] = p[1]; });
    if (C.total < MAX_TOTAL) r.clone().arrayBuffer().then(function(b){
      if (AUTHY.test(url)) { rec.resp_shape = C.shape(new TextDecoder().decode(b)); return; }
      var key = url + '|' + (rec.req || '') + '|' + b.byteLength;
      if (C.seen[key]) { rec.dup = true; return; }
      C.seen[key] = 1; rec.resp = b64(b);
    }).catch(function(e){ rec.note = 'resp: ' + e; });
    return r;
  }, function(e){ rec.err = String(e); rec.ms = Date.now() - t0; throw e; });
};
var X = XMLHttpRequest.prototype, xo = X.open, xs = X.send, xh = X.setRequestHeader;
X.open = function(m, url){ this.__capy = {kind: 'xhr', method: m, url: String(url), page: location.pathname, req_headers: {}}; return xo.apply(this, arguments); };
X.setRequestHeader = function(k, v){ if (this.__capy) { var p = hdr(k, v); this.__capy.req_headers[p[0]] = p[1]; } return xh.apply(this, arguments); };
X.send = function(body){
  var rec = this.__capy, xhr = this;
  if (rec && wanted(rec.url)) {
    rec.t = Date.now();
    try { if (!AUTHY.test(rec.url)) rec.req = bodyOf(body); } catch (e) { rec.note = 'req: ' + e; }
    keep(rec);
    xhr.addEventListener('loadend', function(){
      rec.status = xhr.status; rec.ms = Date.now() - rec.t; rec.resp_headers = {};
      (xhr.getAllResponseHeaders() || '').trim().split(/[\r\n]+/).forEach(function(line){
        var i = line.indexOf(':'); if (i > 0) { var p = hdr(line.slice(0, i).trim(), line.slice(i + 1).trim()); rec.resp_headers[p[0]] = p[1]; } });
      try {
        if (C.total >= MAX_TOTAL) return;
        var r = xhr.response;
        if (AUTHY.test(rec.url)) rec.resp_shape = C.shape(typeof r === 'string' ? r : (r instanceof ArrayBuffer ? new TextDecoder().decode(r) : ''));
        else if (r instanceof ArrayBuffer) rec.resp = b64(r);
        else if (typeof r === 'string') rec.resp = b64(new TextEncoder().encode(r));
      } catch (e) { rec.note = 'resp: ' + e; }
    });
  }
  return xs.apply(this, arguments);
};
var md = navigator.mediaDevices;
if (md && md.getUserMedia) { var gum = md.getUserMedia.bind(md);
  md.getUserMedia = function(c){ var rec = {kind: 'camera', t: Date.now(), page: location.pathname, url: 'getUserMedia', constraints: JSON.stringify(c)};
    keep(rec);
    return gum(c).then(function(s){ rec.status = 'ok'; return s; }, function(e){ rec.status = 'отказ'; rec.err = String(e && (e.name + ': ' + e.message)); throw e; }); }; }
return 'ok';
})()