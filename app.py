import gradio as gr
import azure.cognitiveservices.speech as speechsdk
import asyncio, os, re, hashlib

# --- 配置 ---
SPEECH_KEY = os.environ.get("SPEECH_KEY")
SPEECH_REGION = os.environ.get("SPEECH_REGION")
CACHE_DIR = "tts_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

VOICE_OPTIONS = {
    "👱‍♀️ Katja (标准青年女声)": "de-DE-KatjaNeural",
    "👨 Killian (标准青年男声)": "de-DE-KillianNeural",
    "👨‍💼 Conrad (浑厚新闻男声)": "de-DE-ConradNeural",
    "👩‍🦰 Seraphina (温柔知性女声)": "de-DE-SeraphinaNeural",
    "👦 Kasper (调皮小男孩)": "de-DE-KasperNeural",
    "👧 Maja (可爱小女孩)": "de-DE-MajaNeural"
}
VOICE_NAMES = list(VOICE_OPTIONS.keys())

# --- 核心引擎 ---
def synthesize(text, voice_id, speed):
    hash_val = hashlib.md5(f"{text}{voice_id}{speed}".encode()).hexdigest()
    path = os.path.join(CACHE_DIR, f"{hash_val}.mp3")
    if os.path.exists(path): return path
    
    # SSML 构建
    sp = f"{speed}%" if speed <= 0 else f"+{speed}%"
    ssml = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="de-DE"><voice name="{voice_id}"><prosody rate="{sp}">{text}</prosody></voice></speak>'
    
    cfg = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
    synth = speechsdk.SpeechSynthesizer(cfg, speechsdk.audio.AudioOutputConfig(filename=path))
    synth.speak_ssml_async(ssml).get()
    return path

async def run_tts(script, speed, dv, r1n, r1v, r2n, r2v, r3n, r3v, r4n, r4v):
    if not SPEECH_KEY: raise gr.Error("请在 Render 设置 API Key")
    # 构建角色字典
    mapping = {}
    for n, v in [(r1n, r1v), (r2n, r2v), (r3n, r3v), (r4n, r4v)]:
        if n.strip(): mapping[n.strip().lower()] = VOICE_OPTIONS[v]
    
    def_v = VOICE_OPTIONS[dv]
    lines = script.strip().split('\n')
    tasks = []
    for line in lines:
        if not line.strip(): continue
        m = re.match(r'^([^:：]+)[:：](.+)$', line.strip())
        role, content = (m.group(1).strip().lower(), m.group(2).strip()) if m else (None, line.strip())
        tasks.append(asyncio.to_thread(synthesize, content, mapping.get(role, def_v), speed))
    
    results = await asyncio.gather(*tasks)
    final = os.path.join(CACHE_DIR, f"result_{hashlib.md5(script.encode()).hexdigest()[:6]}.mp3")
    with open(final, 'wb') as f:
        for r in results: f.write(open(r, 'rb').read())
    return final

# --- UI ---
with gr.Blocks(theme=gr.themes.Soft(primary_hue="green")) as app:
    gr.Markdown("## 🇩🇪 德语听说一体机 (4角色增强版)")
    
    with gr.Tab("🎙️ 剧本配音"):
        with gr.Row():
            with gr.Column(scale=2):
                txt = gr.Textbox(lines=10, label="剧本输入", placeholder="旁白: ...\nSophie: ...")
                speed = gr.Slider(-50, 20, 0, step=5, label="语速 (%)")
            with gr.Column(scale=3):
                with gr.Group():
                    dv = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[2], label="[旁白] 默认音色")
                    with gr.Row():
                        r1n = gr.Textbox(label="角色1名", placeholder="Sophie"); r1v = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[0], label="音色")
                    with gr.Row():
                        r2n = gr.Textbox(label="角色2名", placeholder="Tom"); r2v = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[1], label="音色")
                    with gr.Row():
                        r3n = gr.Textbox(label="角色3名"); r3v = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[3], label="音色")
                    with gr.Row():
                        r4n = gr.Textbox(label="角色4名"); r4v = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[4], label="音色")
        btn = gr.Button("🚀 合成全剧音频", variant="primary")
        out = gr.Audio(label="生成结果")
        btn.click(run_tts, [txt, speed, dv, r1n, r1v, r2n, r2v, r3n, r3v, r4n, r4v], out)

    with gr.Tab("👂 口语纠音"):
        mic = gr.Audio(sources="microphone", type="filepath", label="录音")
        rec_btn = gr.Button("🔍 AI 识别内容")
        res = gr.Textbox(label="AI 听到的内容")
        def recognize(audio):
            if not audio: return "请录音"
            c = speechsdk.SpeechConfig(SPEECH_KEY, SPEECH_REGION)
            c.speech_recognition_language = "de-DE"
            r = speechsdk.SpeechRecognizer(c, speechsdk.AudioConfig(filename=audio)).recognize_once_async().get()
            return r.text
        rec_btn.click(recognize, mic, res)

app.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 10000)))
