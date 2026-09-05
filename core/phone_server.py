"""
core/phone_server.py
────────────────────
JARVIS in your pocket — the SAME Jarvis, not a copy.

A tiny web server that runs INSIDE the desktop app and exposes a
mobile chat page. Your phone talks to the exact same brain object the
desktop UI uses: same memory, same agents, same Shopify connection,
same conversation history. One JARVIS, two screens.

On the iPhone:
  1. Same Wi-Fi as the PC → open  http://<PC-IP>:8500  in Safari
  2. Enter the access key (PHONE_KEY in config.py) once
  3. Share button → "Add to Home Screen" → JARVIS icon like a real app

Away from home: install Tailscale (free) on the PC and the iPhone,
sign in with the same account on both, and use the PC's Tailscale
address instead — same page, works from anywhere, fully encrypted.

Security: every request needs the key; wrong key = 401. The server
binds to all interfaces so the phone can reach it; the key plus your
home/Tailscale network is the fence.
"""

import base64
import json
import socket
import threading

import config


def _cfg(name, default):
    # env first (so keys.py 'os.environ[...]' values are honoured),
    # then config.py, then the default. This is why putting
    # PHONE_KEY in keys.py now actually turns the phone on.
    import os as _os
    return _os.environ.get(name) or getattr(config, name, default)


# One request at a time into the brain — the phone and the desktop
# share one mind, so they take turns instead of talking over each other.
_BRAIN_LOCK = threading.Lock()


class _CameraStream:
    """Live PC webcam → phone. Opens the camera only while the phone is
    watching and auto-releases ~12s after the last frame request, so it
    never hogs the webcam from JARVIS's own camera_look. Prefers a fresh
    frame shared by the desktop camera panel if that's already open
    (avoids two processes fighting over one webcam)."""

    def __init__(self, index=0):
        self.index = index
        self.cap = None
        self.latest = None
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.running = False

    def _loop(self):
        import time
        try:
            import cv2
        except Exception:
            self.running = False
            return
        while self.running:
            if time.time() - self.last_request > 12:
                break
            try:
                ok, frame = self.cap.read()
                if ok:
                    enc = cv2.imencode(".jpg", frame,
                                       [cv2.IMWRITE_JPEG_QUALITY, 65])[1]
                    with self.lock:
                        self.latest = enc.tobytes()
            except Exception:
                break
            time.sleep(0.1)
        self._release()

    def _release(self):
        self.running = False
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        self.cap = None
        with self.lock:
            self.latest = None

    def get(self):
        """Latest JPEG bytes, or None if no camera."""
        import time
        self.last_request = time.time()
        # 1) reuse the desktop panel's shared frame if it's fresh
        try:
            import camera as _cam
            shared = _cam._recent_shared_frame()
            if shared:
                return shared
        except Exception:
            pass
        # 2) otherwise run our own capture loop
        if not self.running:
            try:
                import cv2
            except Exception:
                return None
            try:
                self.cap = cv2.VideoCapture(self.index)
                if not self.cap.isOpened():
                    self._release()
                    return None
            except Exception:
                self._release()
                return None
            self.running = True
            threading.Thread(target=self._loop, daemon=True,
                             name="jarvis-cam").start()
        for _ in range(25):            # wait up to ~2.5s for first frame
            with self.lock:
                if self.latest:
                    return self.latest
            time.sleep(0.1)
        return None


_CAM = _CameraStream(int(_cfg("CAMERA_INDEX", 0)))


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#02060d">
<title>ALLISON</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; -webkit-tap-highlight-color:transparent; }
  html, body { height:100%; }
  body { background:#02060d; color:#f1ecfa; font-family:-apple-system,'Segoe UI',sans-serif;
         display:flex; flex-direction:column;
         padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom) 0;
         background-image: radial-gradient(rgba(61,216,255,0.07) 1px, transparent 1px);
         background-size: 26px 26px; }
  header { padding:12px 14px 6px; display:flex; align-items:center; gap:10px; }
  header h1 { font-size:16px; letter-spacing:5px; color:#fff; font-weight:700; }
  header .sub { font-size:8px; color:#5a8bb0; letter-spacing:2.5px; }
  #chips { margin-left:auto; display:flex; gap:6px; }
  .chip { background:rgba(10,22,34,.9); border:1px solid #123048; border-radius:9px;
          padding:5px 9px; text-align:center; }
  .chip .t { font-size:7px; color:#5a8bb0; letter-spacing:1px; }
  .chip .v { font-size:11px; font-weight:700; color:#3dd8ff; }
  .chip .v.gold { color:#ffc85a; }
  #brainwrap { position:relative; height:190px; flex-shrink:0; }
  #brain { width:100%; height:100%; display:block; }
  #state { position:absolute; left:0; right:0; bottom:6px; text-align:center;
           font-size:9px; letter-spacing:3px; color:#5a8bb0; font-weight:700; }
  #state.busy { color:#ffc85a; }
  #memline { position:absolute; left:0; right:0; bottom:-6px; text-align:center;
             font-size:7px; letter-spacing:1.5px; color:#ffc85a99; font-weight:700; }
  #feed { flex:1; overflow-y:auto; padding:14px 12px 8px; display:flex; flex-direction:column;
          gap:8px; -webkit-overflow-scrolling:touch; }
  .msg { max-width:86%; padding:9px 12px; border-radius:13px; font-size:14px; line-height:1.45;
         white-space:pre-wrap; word-wrap:break-word; }
  .you { align-self:flex-end; background:#0e2a3d; border:1px solid #3dd8ff55; border-bottom-right-radius:4px; }
  .jarvis { align-self:flex-start; background:rgba(10,22,34,.92); border:1px solid #123048; border-bottom-left-radius:4px; }
  .who { font-size:8px; letter-spacing:2px; color:#3dd8ff; margin-bottom:3px; font-weight:700; }
  footer { padding:8px 12px calc(8px + env(safe-area-inset-bottom)); border-top:1px solid #123048;
           display:flex; gap:8px; background:rgba(5,7,13,.95); }
  #input { flex:1; background:#0c1c2b; border:1px dashed #3dd8ff44; border-radius:12px;
           padding:11px; color:#f1ecfa; font-size:16px; outline:none; }
  #input:focus { border:1px solid #3dd8ff; }
  /* auto-expanding composer: starts one line, grows with the message,
     caps out and scrolls internally instead of eating the screen */
  #input { resize:none; overflow-y:hidden; line-height:1.4;
           min-height:44px; max-height:34vh; font-family:inherit; }
  #send { width:46px; border:none; border-radius:12px; background:#3dd8ff; color:#04141f;
          font-size:17px; font-weight:700; }
  #send:active { background:#7fe3ff; }
  #mic { width:46px; border:none; border-radius:12px; background:#0c1c2b;
         border:1px solid #123048; color:#3dd8ff; font-size:18px; }
  #mic.listening { background:#3a1220; border-color:#ff5566; color:#ff5566;
                   animation:micpulse 1s infinite; }
  @keyframes micpulse { 50% { box-shadow:0 0 14px #ff556699; } }
  #tools { display:flex; gap:6px; margin-left:auto; }
  .tool { width:34px; height:34px; border-radius:9px; background:rgba(10,22,34,.9);
          border:1px solid #123048; color:#5a8bb0; font-size:15px; }
  .tool.on { border-color:#3dd8ff; color:#3dd8ff; background:#0e2438; }
  #chips { display:flex; gap:6px; margin-left:8px; }
  #camview { position:fixed; inset:0; z-index:20; background:#000;
             display:flex; flex-direction:column; align-items:center; justify-content:center;
             padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  #camview.hidden { display:none; }
  #camtop { position:absolute; top:calc(env(safe-area-inset-top) + 10px); left:0; right:0;
            display:flex; align-items:center; justify-content:space-between; padding:0 18px;
            color:#3dd8ff; font-size:11px; letter-spacing:3px; font-weight:700; }
  #camclose { background:none; border:none; color:#fff; font-size:30px; line-height:1; }
  #camimg { max-width:100%; max-height:78%; border:1px solid #123048; border-radius:10px;
            background:#0c1c2b; }
  #camnote { position:absolute; bottom:calc(env(safe-area-inset-bottom) + 18px);
             color:#5a8bb0; font-size:11px; letter-spacing:1px; }
  #seeview { position:fixed; inset:0; z-index:21; background:#000;
             display:flex; flex-direction:column; align-items:center; justify-content:center;
             padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  #seeview.hidden { display:none; }
  #seevid { max-width:100%; max-height:70%; border:1px solid #123048; border-radius:12px; background:#0c1c2b; object-fit:cover; }
  #seenote { position:absolute; bottom:calc(env(safe-area-inset-bottom) + 90px);
             color:#5a8bb0; font-size:12px; letter-spacing:1px; text-align:center; padding:0 24px; }
  #seecap { position:absolute; bottom:calc(env(safe-area-inset-bottom) + 26px);
            background:#3dd8ff; color:#04141f; border:none; border-radius:30px;
            padding:14px 34px; font-size:15px; font-weight:800; letter-spacing:1px; }
  #seecap:active { background:#7fe3ff; }
  #seeask { position:absolute; left:16px; right:16px;
    bottom:calc(env(safe-area-inset-bottom) + 84px);
    background:rgba(4,20,31,.92); color:#dff2ff; border:1px solid #123048;
    border-radius:12px; padding:13px 15px; font-size:16px; outline:none;
    -webkit-appearance:none; }
  #seeask::placeholder { color:#5f7d95; }
  /* a panel she pushes back — an image, a diagram, search results */
  /* HIDDEN MEANS HIDDEN.
     This used to hide itself with transform:translateY(105%), which
     moves the panel down by 105% of ITS OWN height — about 85px when
     empty. That was nowhere near enough to clear the screen, so the
     shelf sat directly on top of the message box: a blue bar where the
     composer should be. Verified in a real browser: elementFromPoint
     over the input returned "shelfbar".
     Visibility + pointer-events do not depend on the element's height,
     so this cannot come back. */
  #shelf { position:fixed; left:0; right:0;
    bottom:calc(env(safe-area-inset-bottom) + 74px); z-index:15;
    max-height:52vh; overflow-y:auto; background:#04141f;
    border-top:1px solid #123048; box-shadow:0 -14px 40px rgba(0,0,0,.6);
    visibility:hidden; opacity:0; pointer-events:none;
    transform:translateY(14px);
    transition:opacity .22s ease, transform .22s ease, visibility .22s; }
  #shelf.up { visibility:visible; opacity:1; pointer-events:auto;
    transform:translateY(0); }
  #shelfbar { display:flex; align-items:center; justify-content:space-between;
    padding:11px 15px; border-bottom:1px solid #123048;
    color:#3dd8ff; font-size:12px; letter-spacing:2px; font-weight:700; }
  #shelfclose { background:none; border:none; color:#7fe3ff; font-size:23px; }
  #shelfbody { padding:15px; color:#dff2ff; font-size:15px;
    white-space:pre-wrap; line-height:1.55; }
  #shelfbody img { width:100%; border-radius:10px; display:block; }

  #seecap.busy { background:#0c1c2b; color:#3dd8ff; border:1px solid #123048; }
  #keywrap { position:fixed; inset:0; background:#02060d; display:flex; flex-direction:column;
             align-items:center; justify-content:center; gap:14px; padding:30px; z-index:10; }
  #keywrap.hidden { display:none; }
  #keywrap h2 { color:#3dd8ff; letter-spacing:6px; font-size:22px; }
  #keywrap p { color:#5a8bb0; font-size:12px; text-align:center; }
  #key { background:#0c1c2b; border:1px solid #123048; border-radius:12px; padding:12px 16px;
         color:#f1ecfa; font-size:16px; text-align:center; letter-spacing:3px; outline:none; width:230px; }
  #unlock { background:#3dd8ff; color:#04141f; border:none; border-radius:12px;
            padding:12px 34px; font-size:14px; font-weight:700; letter-spacing:2px; }
</style>
</head>
<body>
  <div id="keywrap">
    <canvas id="lockbrain" width="220" height="150"></canvas>
    <h2>ALLISON</h2>
    <p>Enter your access key, sir.</p>
    <input id="key" type="password" placeholder="access key" autocomplete="off">
    <button id="unlock">UNLOCK</button>
  </div>
  <header>
    <div><h1>ALLISON</h1><div class="sub">POCKET &middot; SAME BRAIN</div></div>
    <div id="tools">
      <button class="tool" id="t_speak" title="Speak replies">&#128266;</button>
      <button class="tool" id="t_see" title="Identify with your camera">&#128248;</button>
      <button class="tool" id="t_cam" title="PC camera">&#128247;</button>
      <button class="tool" id="t_pick" title="Share a photo">&#128193;</button>
      <input type="file" id="picker" accept="image/*" style="display:none">
    </div>
    <div id="chips">
      <div class="chip"><div class="t">BALANCE</div><div class="v gold" id="c_bal">—</div></div>
      <div class="chip"><div class="t">TODAY</div><div class="v" id="c_cost">—</div></div>
    </div>
  </header>
  <div id="camview" class="hidden">
    <div id="camtop"><span>PC CAMERA &middot; LIVE</span><button id="camclose">&times;</button></div>
    <img id="camimg" alt="camera">
    <div id="camnote">Live from the PC webcam, sir.</div>
  </div>
  <div id="shelf">
  <div id="shelfbar"><span id="shelftitle">ALLISON</span>
    <button id="shelfclose">&times;</button></div>
  <div id="shelfbody"></div>
</div>

<div id="seeview" class="hidden">
    <div id="camtop"><span>SHOW ALLISON &middot; POINT &amp; IDENTIFY</span><button id="seeclose">&times;</button></div>
    <video id="seevid" playsinline autoplay muted></video>
    <div id="seenote">Point at something, then ask — or just tap Identify.</div>
    <input id="seeask" placeholder="Ask about this… e.g. how does it work?"
           autocomplete="off" autocapitalize="sentences">
    <button id="seecap">◉ Ask Allison</button>
  </div>
  <div id="brainwrap">
    <canvas id="brain"></canvas>
    <div id="state">STANDING BY</div>
    <div id="memline"></div>
  </div>
  <div id="feed"></div>
  <footer>
    <button id="mic" title="Talk">&#127908;</button>
    <textarea id="input" rows="1" placeholder="Message Allison…" autocomplete="off"></textarea>
    <button id="send">➤</button>
  </footer>
<script>
/* ── the SAME brain as the desk — ported point-for-point ── */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function brainPoints(n, seed){
  const rng = mulberry32(seed); const pts=[]; let tries=0;
  while(pts.length<n && tries<n*40){
    tries++;
    const u=rng()*Math.PI*2, v=Math.acos(rng()*2-1);
    let x=Math.sin(v)*Math.cos(u)*1.15, y=Math.sin(v)*Math.sin(u)*0.82, z=Math.cos(v)*1.35;
    if(y<0) y*=0.72;
    if(Math.abs(x)<0.09 && y>-0.1 && rng()<0.85) continue;      /* central fissure */
    const fold=0.05*Math.sin(6*u+3*v)+0.045*Math.sin(9*v)+0.035*Math.sin(7*u);
    x*=1+fold; y*=1+fold; z*=1+fold;
    if(z>0.6) y+=0.05;
    pts.push([x,y,z, rng()*Math.PI*2]);
  }
  return pts;
}
const PTS = brainPoints(650, 23);
/* stable shuffled order for gold memory dots — like the desk (seed 7) */
const ORDER = PTS.map((_,i)=>i);
{ const r=mulberry32(7); for(let i=ORDER.length-1;i>0;i--){const j=Math.floor(r()*(i+1));[ORDER[i],ORDER[j]]=[ORDER[j],ORDER[i]];} }
let memCount=0, thinking=false, yaw=0.5, t=0, energy=0;

function drawBrain(cv, scale){
  const ctx=cv.getContext('2d');
  const W=cv.width, H=cv.height, cx=W/2, cy=H/2, R=Math.min(W,H)*(scale||0.42);
  ctx.clearRect(0,0,W,H);
  const target = thinking?1:0.12;
  energy += (target-energy)*0.06;
  t += 0.016+energy*0.02; yaw += 0.0045+energy*0.006;
  const memSet=new Set(ORDER.slice(0, Math.min(PTS.length, memCount)));
  const cy2=Math.cos(yaw), sy2=Math.sin(yaw), wave=Math.sin(t*1.5)*1.35;
  const proj=[];
  for(let i=0;i<PTS.length;i++){
    const p=PTS[i];
    const x1=p[0]*cy2+p[2]*sy2, z1=-p[0]*sy2+p[2]*cy2;
    const f=1.7/(z1+2.6);
    proj.push([cx+x1*R*f, cy-p[1]*R*f*1.05, z1, i, p[2], p[3]]);
  }
  proj.sort((a,b)=>a[2]-b[2]);
  for(const q of proj){
    const d=Math.max(0.2,Math.min(1,(q[2]+1.4)/2.8));
    const tw=0.7+0.3*Math.sin(t*1.2+q[5]);
    let r,g,b,sz,alpha;
    if(memSet.has(q[3])){ r=255;g=200;b=90; sz=1.5+1.1*d; alpha=(0.55+0.4*d)*(0.75+0.25*Math.sin(t*1.6+q[5])); }
    else{
      const hit=energy>0.03?Math.max(0,1-Math.abs(q[4]-wave)*3)*energy:0;
      r=34+(255-34)*hit; g=211+(255-211)*hit; b=238+(255-238)*hit;
      sz=0.8+0.7*d; alpha=(0.32+0.55*d)*tw;
    }
    ctx.fillStyle='rgba('+(r|0)+','+(g|0)+','+(b|0)+','+alpha.toFixed(2)+')';
    ctx.beginPath(); ctx.arc(q[0],q[1],sz,0,6.283); ctx.fill();
  }
  /* platform rings */
  const py=cy+R*1.18, rx=R*1.05, ry=rx*0.22;
  for(let k=0;k<3;k++){
    ctx.strokeStyle='rgba(61,216,255,'+(0.35-k*0.1+energy*0.2)+')'; ctx.lineWidth=k===0?1.2:0.7;
    ctx.beginPath(); ctx.ellipse(cx,py,rx*(1-k*0.28),ry*(1-k*0.28),0,0,6.283); ctx.stroke();
  }
  /* spinner arc when busy */
  if(energy>0.3){
    ctx.strokeStyle='rgba(255,200,90,'+(0.7*energy)+')'; ctx.lineWidth=1.6;
    const a0=(t*4)%6.283;
    ctx.beginPath(); ctx.arc(cx,cy,R*1.15,a0,a0+1.2); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx,cy,R*1.15,a0+3.14,a0+4.34); ctx.stroke();
  }
}
const brainCv=document.getElementById('brain');
function sizeCanvas(){ const r=brainCv.getBoundingClientRect();
  brainCv.width=r.width*devicePixelRatio; brainCv.height=r.height*devicePixelRatio; }
sizeCanvas(); addEventListener('resize', sizeCanvas);
const lockCv=document.getElementById('lockbrain');
(function loop(){ drawBrain(brainCv,0.40);
  if(!document.getElementById('keywrap').classList.contains('hidden')) drawBrain(lockCv,0.42);
  requestAnimationFrame(loop); })();

/* ── chat ── */
const feed=document.getElementById('feed'), input=document.getElementById('input');
const keywrap=document.getElementById('keywrap'), stateEl=document.getElementById('state');
let KEY=localStorage.getItem('jarvis_key')||'';
function addMsg(text,who){ const d=document.createElement('div'); d.className='msg '+who;
  const w=document.createElement('div'); w.className='who'; w.textContent=who==='you'?'YOU':'ALLISON';
  d.appendChild(w); d.appendChild(document.createTextNode(text));
  feed.appendChild(d); feed.scrollTop=feed.scrollHeight; return d; }
function setState(busy){ thinking=busy;
  stateEl.textContent=busy?'THINKING…':'STANDING BY';
  stateEl.className=busy?'busy':''; }

async function refreshStatus(){
  if(!KEY) return;
  try{ const r=await fetch('/api/status',{headers:{'X-Jarvis-Key':KEY}});
    if(!r.ok) return; const s=await r.json();
    memCount=Math.round((s.memories||0)*650/1250);
    document.getElementById('memline').textContent=(s.memories||0)+' MEMORIES FORMED';
    document.getElementById('c_bal').textContent=s.balance==null?'—':('$'+Number(s.balance).toFixed(2));
    document.getElementById('c_cost').textContent=s.cost_today==null?'—':('$'+Number(s.cost_today).toFixed(2));
  }catch(e){} }
setInterval(refreshStatus, 15000);

async function checkKey(){ if(!KEY) return false;
  try{ const r=await fetch('/api/ping',{headers:{'X-Jarvis-Key':KEY}}); return r.ok; }catch(e){ return false; } }
async function boot(){ if(await checkKey()){ keywrap.classList.add('hidden'); refreshStatus();
  addMsg('Online, sir. Same mind as the command centre — wherever you are.', 'jarvis'); } }
boot();
document.getElementById('unlock').onclick=async()=>{
  KEY=document.getElementById('key').value.trim(); localStorage.setItem('jarvis_key',KEY);
  if(await checkKey()){ keywrap.classList.add('hidden'); refreshStatus();
    addMsg('Online, sir. Same mind as the command centre — wherever you are.', 'jarvis'); }
  else{ document.getElementById('key').value=''; document.getElementById('key').placeholder='wrong key — try again'; } };

async function send(){
  const text=input.value.trim(); if(!text) return;
  input.value=''; try{ autoGrow(); }catch(e){}
  addMsg(text,'you'); setState(true);
  try{
    const r=await fetch('/api/chat',{method:'POST',
      headers:{'Content-Type':'application/json','X-Jarvis-Key':KEY},
      body:JSON.stringify({text})});
    const data=await r.json();
    const reply=data.reply||data.error||'(no reply)';
    addMsg(reply,'jarvis'); say(reply);
    if(j.panel){ showShelf(j.panel.title, j.panel.body, j.panel.image); }
    refreshStatus();
  }catch(e){ addMsg('Connection lost, sir — is the PC on and Allison running?','jarvis'); }
  setState(false);
}
document.getElementById('send').onclick=send;
input.addEventListener('keydown',e=>{ if(e.key==='Enter') send(); });

/* ── HIS VOICE — speak replies aloud (browser TTS, iOS-friendly) ── */
let speakOn = localStorage.getItem('jarvis_speak')==='1';
const tSpeak = document.getElementById('t_speak');
function pickVoice(){
  const vs = speechSynthesis.getVoices();
  return vs.find(v=>/en-GB/i.test(v.lang)&&/daniel|arthur|male/i.test(v.name))
      || vs.find(v=>/en-GB/i.test(v.lang))
      || vs.find(v=>/^en/i.test(v.lang)) || null;
}
function say(text){
  if(!speakOn || !window.speechSynthesis) return;
  const clean = text.replace(/[*_`#>]/g,'').replace(/https?:\\/\\/\\S+/g,'a link').slice(0,600);
  const u = new SpeechSynthesisUtterance(clean);
  const v = pickVoice(); if(v) u.voice=v; u.rate=1.0; u.pitch=0.95;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}
function reflectSpeak(){ tSpeak.classList.toggle('on', speakOn); }
reflectSpeak();
tSpeak.onclick = ()=>{
  speakOn = !speakOn; localStorage.setItem('jarvis_speak', speakOn?'1':'0');
  reflectSpeak();
  if(speakOn && window.speechSynthesis){ // unlock iOS TTS within this tap
    const u=new SpeechSynthesisUtterance('Voice on, sir.');
    const v=pickVoice(); if(v)u.voice=v; speechSynthesis.speak(u);
  } else if(window.speechSynthesis){ speechSynthesis.cancel(); }
};
if(window.speechSynthesis) speechSynthesis.onvoiceschanged = ()=>{};

/* ── YOUR VOICE — speak to him (Web Speech; graceful fallback) ── */
const micBtn = document.getElementById('mic');
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let hintedMic = false;
function micHint(){ if(!hintedMic){ hintedMic=true;
  addMsg("Best voice, sir: tap the message box, then the 🎤 on your keyboard, and speak — Apple's dictation is spot-on.", 'jarvis'); } }
micBtn.onclick = ()=>{
  input.focus();               // pop the keyboard so its 🎤 is one tap away
  if(!SR){ micHint(); return; }
  const r = new SR(); r.lang='en-GB'; r.interimResults=false; r.maxAlternatives=1;
  micBtn.classList.add('listening');
  r.onresult = e=>{ input.value = e.results[0][0].transcript; };
  r.onend = ()=>{ micBtn.classList.remove('listening'); if(input.value.trim()) send(); };
  r.onerror = ()=>{ micBtn.classList.remove('listening'); micHint(); };
  try{ r.start(); }catch(e){ micBtn.classList.remove('listening'); micHint(); }
};

/* ── PC CAMERA on your phone ── */
const camView=document.getElementById('camview'), camImg=document.getElementById('camimg');
const camNote=document.getElementById('camnote');
let camTimer=null;
function openCam(){
  camView.classList.remove('hidden');
  camNote.textContent='Connecting to the PC webcam…';
  const tick=()=>{
    const img=new Image();
    img.onload=()=>{ camImg.src=img.src; camNote.textContent='Live from the PC webcam, sir.'; };
    img.onerror=()=>{ camNote.textContent='Camera unavailable — is the PC on with a webcam?'; };
    img.src='/api/camera?k='+encodeURIComponent(KEY)+'&t='+Date.now();
  };
  tick(); camTimer=setInterval(tick, 700);
}
function closeCam(){ camView.classList.add('hidden'); if(camTimer){clearInterval(camTimer);camTimer=null;} camImg.removeAttribute('src'); }
document.getElementById('t_cam').onclick=openCam;
document.getElementById('camclose').onclick=closeCam;

/* ── SHOW ALLISON: use YOUR phone's back camera to identify a part ── */
const seeView=document.getElementById('seeview'), seeVid=document.getElementById('seevid'),
      seeNote=document.getElementById('seenote'), seeCap=document.getElementById('seecap');
let seeStream=null;
async function openSee(){
  seeView.classList.remove('hidden');
  seeNote.textContent='Starting your camera…';
  try{
    seeStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
    seeVid.srcObject=seeStream;
    seeNote.textContent='Point at a part, then tap Identify.';
  }catch(e){
    seeNote.textContent='Could not open the camera — allow camera access in your browser, then tap 📸 again.';
  }
}
function closeSee(){
  seeView.classList.add('hidden');
  if(seeStream){ seeStream.getTracks().forEach(t=>t.stop()); seeStream=null; }
  seeVid.srcObject=null; seeCap.classList.remove('busy'); seeCap.textContent='◉ Identify this';
}
// ── the shelf: how she shows me things, instead of only telling me ──
const shelf=document.getElementById('shelf'),
      shelfBody=document.getElementById('shelfbody'),
      shelfTitle=document.getElementById('shelftitle');
function showShelf(title, body, imageURL){
  shelfTitle.textContent=(title||'ALLISON').toUpperCase();
  shelfBody.innerHTML='';
  if(imageURL){ const im=new Image(); im.src=imageURL; shelfBody.appendChild(im); }
  if(body){ const p=document.createElement('div');
            p.style.marginTop=imageURL?'12px':'0'; p.textContent=body;
            shelfBody.appendChild(p); }
  shelf.classList.add('up');
}
document.getElementById('shelfclose').onclick=()=>shelf.classList.remove('up');

// send an image + an optional question, from the camera OR the gallery
async function askAboutImage(dataURL, question, label){
  addMsg(label||(question?('📸 '+question):'📸 (showed Allison something)'),'you');
  setState(true);
  showShelf('LOOKING AT THIS', question||'', dataURL);
  try{
    const r=await fetch('/api/see',{method:'POST',
      headers:{'Content-Type':'application/json','X-Jarvis-Key':KEY},
      body:JSON.stringify({image:dataURL, question:question||''})});
    const j=await r.json();
    const reply=j.reply||j.error||'I could not make that out, sir.';
    addMsg(reply,'jarvis');
    showShelf(j.label||'WHAT I SEE', reply, dataURL);
    if(j.reply) speak(j.reply);
  }catch(e){ addMsg('Connection lost, sir — is the PC on and Allison running?','jarvis'); }
  setState(false);
}

function frameToDataURL(video){
  const c=document.createElement('canvas');
  const w=video.videoWidth||640, h=video.videoHeight||480;
  const scale=Math.min(1, 1280/Math.max(w,h));
  c.width=Math.round(w*scale); c.height=Math.round(h*scale);
  c.getContext('2d').drawImage(video,0,0,c.width,c.height);
  return c.toDataURL('image/jpeg',0.82);
}

async function captureSee(){
  if(!seeStream||seeCap.classList.contains('busy')) return;
  seeCap.classList.add('busy'); seeCap.textContent='Allison is looking…';
  const dataURL=frameToDataURL(seeVid);
  const q=(document.getElementById('seeask').value||'').trim();
  closeSee();
  await askAboutImage(dataURL, q);
}

// share an existing photo from the gallery
const picker=document.getElementById('picker');
document.getElementById('t_pick').onclick=()=>picker.click();
picker.onchange=function(){
  const f=this.files && this.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=async e=>{
    const q=prompt('Ask about this photo (or leave blank to identify it):')||'';
    await askAboutImage(e.target.result, q.trim(), q.trim()? ('🖼 '+q.trim()) : '🖼 (shared a photo)');
  };
  rd.readAsDataURL(f);
  this.value='';
};
document.getElementById('t_see').onclick=openSee;
document.getElementById('seeclose').onclick=closeSee;
seeCap.onclick=captureSee;

// ── ONE CONVERSATION, TWO WINDOWS ──────────────────────────────────
// The phone keeps no transcript of its own. It holds a cursor and asks
// the backend what has been said since — by EITHER device. So a message
// typed on the PC shows up here, and a photo taken here shows up there,
// without anyone refreshing anything.
let CURSOR = 0, syncing = false;
const seenIds = new Set();

function renderShared(m){
  if(seenIds.has(m.id)) return;
  seenIds.add(m.id);
  if(m.role === 'user'){
    // our own sends are already on screen; only mirror the OTHER window
    if(m.source === 'phone') return;
    addMsg(m.text + '   · from the PC', 'you');
  } else if(m.role === 'allison'){
    if(m.source === 'phone') return;      // already shown locally
    addMsg(m.text, 'jarvis');
  }
}

async function syncShared(){
  if(syncing) return;
  syncing = true;
  try{
    const r = await fetch('/api/events?since=' + CURSOR,
                          {headers:{'X-Jarvis-Key':KEY}});
    if(r.ok){
      const j = await r.json();
      if(j.shared){
        (j.messages||[]).forEach(renderShared);
        if(typeof j.cursor === 'number') CURSOR = j.cursor;
        if(j.status && j.status.state){
          const busy = j.status.state === 'working';
          const st = document.getElementById('state');
          if(st && !st.dataset.localBusy){
            st.textContent = busy ? (j.status.activity || 'WORKING') : 'STANDING BY';
            st.className = busy ? 'busy' : '';
          }
        }
      }
    }
  }catch(e){ /* offline: keep the last view, try again shortly */ }
  syncing = false;
}
setInterval(syncShared, 1500);
syncShared();

// ── auto-expanding composer ────────────────────────────────────────
// Height is recomputed from scrollHeight on every keystroke, so it
// grows with WRAPPED text too, not just hard newlines. Caps at the CSS
// max-height and then scrolls inside itself.
const composer = document.getElementById('input');
function autoGrow(){
  composer.style.height = 'auto';
  const max = parseFloat(getComputedStyle(composer).maxHeight) || 260;
  const h = Math.min(composer.scrollHeight, max);
  composer.style.height = h + 'px';
  composer.style.overflowY = (composer.scrollHeight > max) ? 'auto' : 'hidden';
}
composer.addEventListener('input', autoGrow);
composer.addEventListener('keydown', function(e){
  // Enter sends, Shift+Enter makes a new line — same as the desk
  if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(); }
});
autoGrow();
</script>
</body>
</html>"""


def _img_data_url(path, max_bytes=3_500_000):
    """Local image file -> data URL the phone can render inline.

    She saves screenshots, drawings and camera frames to disk and shows
    them on the desktop HUD. The phone has no access to that filesystem,
    so anything she wants to SHOW has to travel as bytes.
    """
    try:
        import mimetypes
        import os as _os
        if not path or not _os.path.exists(path):
            return ""
        if _os.path.getsize(path) > max_bytes:
            return ""
        mime = mimetypes.guess_type(path)[0] or "image/png"
        if not mime.startswith("image/"):
            return ""
        with open(path, "rb") as f:
            return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_phone_server(brain):
    """Start the pocket-JARVIS server in a daemon thread. Returns the
    URL (or None if disabled/unavailable)."""
    if not _cfg("PHONE_SERVER_ENABLED", True):
        print("[Phone] disabled in config.")
        return None
    key = str(_cfg("PHONE_KEY", "") or "").strip()
    if not key:
        print("[Phone] no PHONE_KEY set in config.py — phone access off. "
              "Add: PHONE_KEY = 'something-secret'")
        return None
    try:
        from flask import Flask, request, jsonify, Response
    except ImportError:
        print("[Phone] Flask not installed — run: pip install flask")
        return None

    port = int(_cfg("PHONE_SERVER_PORT", 8500))
    app = Flask("jarvis_phone")

    def _authed():
        # header for API calls; ?k= query param for <img> camera src which
        # can't send custom headers. Over Tailscale both are encrypted.
        return (request.headers.get("X-Jarvis-Key", "") == key
                or request.args.get("k", "") == key)

    @app.route("/")
    def page():
        return PAGE

    @app.route("/api/ping")
    def ping():
        if not _authed():
            return jsonify({"error": "unauthorised"}), 401
        return jsonify({"ok": True})

    @app.route("/api/chat", methods=["POST"])
    def chat():
        if not _authed():
            return jsonify({"error": "unauthorised"}), 401
        try:
            text = (request.get_json(force=True) or {}).get("text", "").strip()
        except Exception:
            text = ""
        if not text:
            return jsonify({"error": "empty message"}), 400
        try:
            # take turns with the desktop — one shared mind
            with _BRAIN_LOCK:
                # Capture any panel she raises while thinking, so "show
                # me X" on the phone SHOWS something instead of just
                # describing it. Same show_panel call the desktop HUD
                # uses; we just also forward it down the wire.
                grabbed = {}
                original = getattr(brain, "show_panel", None)

                def _capture(panel_id, title, content, kind="text", **kw):
                    try:
                        grabbed["title"] = str(title)
                        if kind == "image":
                            grabbed["image"] = _img_data_url(str(content))
                            grabbed["body"] = ""
                        else:
                            grabbed["body"] = str(content)[:4000]
                    except Exception:
                        pass
                    if callable(original):
                        try:
                            return original(panel_id, title, content,
                                            kind=kind, **kw)
                        except Exception:
                            return None

                if callable(original):
                    brain.show_panel = _capture
                try:
                    reply = brain.process(text, source="phone")
                finally:
                    if callable(original):
                        brain.show_panel = original

            out = {"reply": str(reply)}
            if grabbed.get("body") or grabbed.get("image"):
                out["panel"] = {"title": grabbed.get("title", "ALLISON"),
                                "body": grabbed.get("body", ""),
                                "image": grabbed.get("image", "")}
            return jsonify(out)
        except Exception as e:
            return jsonify({"error": f"brain error: {e}"}), 500

    @app.route("/api/see", methods=["POST"])
    def see():
        # phone back-camera → Allison identifies what you're showing her
        if not _authed():
            return jsonify({"error": "unauthorised"}), 401
        try:
            data = request.get_json(force=True) or {}
        except Exception:
            data = {}
        img = data.get("image", "")
        question = (data.get("question", "") or "").strip()
        if not img:
            return jsonify({"error": "no image"}), 400
        # strip the data-URL prefix ("data:image/jpeg;base64,....")
        if "," in img:
            img = img.split(",", 1)[1]
        try:
            jpeg = base64.b64decode(img)
        except Exception:
            return jsonify({"error": "bad image data"}), 400
        if not jpeg:
            return jsonify({"error": "empty image"}), 400
        try:
            with _BRAIN_LOCK:
                reply = brain.identify_image(jpeg, question)
            out = {"reply": str(reply)}
            # pull the object name out so the phone can title the panel
            try:
                import re as _re
                m = _re.match(r"That's ([^,.]{2,60})[,.]", str(reply))
                if m:
                    out["label"] = m.group(1).strip().upper()
            except Exception:
                pass
            return jsonify(out)
        except Exception as e:
            return jsonify({"error": f"brain error: {e}"}), 500

    @app.route("/api/events")
    def events():
        """Everything said on ANY device since `since`.

        Cursor-based rather than a full transcript dump: the phone sends
        the highest id it has, gets only what is new, and cannot miss or
        duplicate a message. Passing since=0 returns recent history, so
        opening the phone mid-conversation shows what has already been
        said instead of a blank page.
        """
        if not _authed():
            return jsonify({"error": "unauthorised"}), 401
        sess = getattr(brain, "session", None)
        if sess is None:
            return jsonify({"messages": [], "cursor": 0,
                            "status": {"state": "standing_by"},
                            "shared": False})
        try:
            since = request.args.get("since", "0")
            out = sess.since(since)
            out["shared"] = True
            return jsonify(out)
        except Exception as e:
            return jsonify({"error": f"session error: {e}"}), 500

    @app.route("/api/camera")
    def camera_frame():
        if not _authed():
            return jsonify({"error": "unauthorised"}), 401
        jpg = _CAM.get()
        if not jpg:
            return jsonify({"error": "camera unavailable"}), 503
        return Response(jpg, mimetype="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.route("/api/status")
    def status():
        if not _authed():
            return jsonify({"error": "unauthorised"}), 401
        out = {"activity": getattr(brain, "current_activity", "?")}
        try:
            ct = getattr(brain, "cost_tracker", None)
            if ct:
                out["cost_today"] = ct.today_cost()
                if hasattr(ct, "remaining_balance"):
                    out["balance"] = ct.remaining_balance()
        except Exception:
            pass
        # memories — so the pocket brain glows gold like the desk one
        try:
            n = 0
            mem = getattr(brain, "memory", None)
            if mem:
                n += len(mem.get_all())
            res = getattr(brain, "researcher", None)
            if res and getattr(res, "knowledge", None):
                n += len(res.knowledge)
            out["memories"] = n
        except Exception:
            out["memories"] = 0
        return jsonify(out)

    def _run():
        # quiet flask logging — keep the JARVIS console clean
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False,
                threaded=True)

    threading.Thread(target=_run, daemon=True, name="jarvis-phone").start()
    url = f"http://{_local_ip()}:{port}"
    print(f"[Phone] Pocket ALLISON live → {url}  (key required)")
    return url
