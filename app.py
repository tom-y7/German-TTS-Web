import gradio as gr
import azure.cognitiveservices.speech as speechsdk
import asyncio, os, re, hashlib

# --- 1. 基础配置 ---
SPEECH_KEY = os.environ.get("SPEECH_KEY")
SPEECH_REGION = os.environ.get("SPEECH_REGION")
CACHE_DIR = "tts_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

VOICE_OPTIONS = {
    "👱‍♀️ Katja (支持全情感-推荐)": "de-DE-KatjaNeural",
    "👨 Killian (青年男声)": "de-DE-KillianNeural",
    "👨‍💼 Conrad (新闻男声)": "de-DE-ConradNeural",
    "👩‍🦰 Seraphina (知性女声)": "de-DE-SeraphinaNeural",
    "👦 Kasper (小男孩)": "de-DE-KasperNeural",
    "👧 Maja (小女孩)": "de-DE-MajaNeural",
    "👩‍🦳 Lou (熟女声)": "de-DE-LouNeural",
    "👨‍🦳 Bernd (中年男声)": "de-DE-BerndNeural"
}
VOICE_NAMES = list(VOICE_OPTIONS.keys())
MAX_ROLES = 8

# --- 2. 情感扫描仪 (自动挡核心) ---
def detect_emotion(text):
    """根据关键词和标点符号自动匹配 Azure 情感风格"""
    t = text.lower()
    # 兴奋/高兴：关键词或感叹号
    if any(w in t for w in ["toll", "super", "freue", "schön", "wunderbar", "glück", "prima"]) or "!" in t:
        return "cheerful"
    # 难过/遗憾
    if any(w in t for w in ["leider", "schade", "traurig", "entschuldigung", "tut mir leid"]):
        return "sad"
    # 悄悄话：关键词或括号
    if any(w in t for w in ["psst", "leise", "geheim"]) or ("(" in t and ")" in t):
        return "whispering"
    # 默认：正式/平稳
    return "general"

# --- 3. 核心合成逻辑 ---
def synthesize(text, voice_id, speed):
    hash_val = hashlib.md5(f"{text}{voice_id}{speed}".encode()).hexdigest()
    path = os.path.join(CACHE_DIR, f"{hash_val}.mp3")
    if os.path.exists(path): return path
    
    emotion = detect_emotion(text)
    sp = f"{speed}%" if speed <= 0 else f"+{speed}%"
    
    # 构建带情感标签的 SSML
    ssml = f'''
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" 
           xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="de-DE">
        <voice name="{voice_id}">
            <mstts:express-as style="{emotion}">
                <prosody rate="{sp}">{text}</prosody>
            </mstts:express-as>
        </voice>
    </speak>
    '''
    
    cfg = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
    synth = speechsdk.SpeechSynthesizer(cfg, speechsdk.audio.AudioOutputConfig(filename=path))
    synth.speak_ssml_async(ssml).get()
    return path

async def run_tts(script, speed, dv, *role_args):
    if not SPEECH_KEY: raise gr.Error("请检查 Render 环境变量 SPEECH_KEY")
    mapping = {}
    for i in range(0, len(role_args), 2):
        name, voice = role_args[i], role_args[i+1]
        if name and name.strip(): mapping[name.strip().lower()] = VOICE_OPTIONS[voice]
    
    def_v = VOICE_OPTIONS[dv]
    lines = [l.strip() for l in script.strip().split('\n') if l.strip()]
    tasks = [asyncio.to_thread(synthesize, 
             (re.match(r'^([^:：]+)[:：](.+)$', l).group(2).strip() if re.match(r'^([^:：]+)[:：](.+)$', l) else l),
             mapping.get(re.match(r'^([^:：]+)[:：](.+)$', l).group(1).strip().lower() if re.match(r'^([^:：]+)[:：](.+)$', l) else None, def_v),
             speed) for l in lines]
    
    results = await asyncio.gather(*tasks)
    final = os.path.join(CACHE_DIR, f"final_{hashlib.md5(script.encode()).hexdigest()[:6]}.mp3")
    with open(final, 'wb') as f:
        for r in results: f.write(open(r, 'rb').read())
    return final

# --- 4. UI 界面 ---
with gr.Blocks(theme=gr.themes.Soft(primary_hue="green")) as app:
    gr.Markdown("# 🎭 德语 AI 剧本大师 Pro\n*(支持自动情感识别 & 动态 8 角色)*")
    
    with gr.Tab("🎬 录音棚"):
        with gr.Row():
            with gr.Column(scale=2):
                txt = gr.Textbox(lines=12, label="输入剧本", placeholder="Sophie: Das ist super! (开心)\nHans: Es tut mir leid... (难过)")
                speed = gr.Slider(-50, 20, 0, step=5, label="全局语速 (%)")
                btn = gr.Button("🚀 合成带情感的音频", variant="primary", size="lg")
            with gr.Column(scale=3):
                dv = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[0], label="默认音色 (建议选 Katja)")
                role_inputs, role_rows = [], []
                for i in range(MAX_ROLES):
                    with gr.Row(visible=(i < 2)) as row:
                        n = gr.Textbox(label=f"角色{i+1}名", placeholder="如: Sophie", scale=1)
                        v = gr.Dropdown(VOICE_NAMES, value=VOICE_NAMES[i % len(VOICE_NAMES)], label="音色", scale=2)
                        role_inputs.extend([n, v]); role_rows.append(row)
                with gr.Row():
                    add_btn = gr.Button("➕ 增加角色"); rem_btn = gr.Button("➖ 减少角色")
                v_count = gr.State(2)
                def up(c, a):
                    c = min(MAX_ROLES, c+1) if a=="add" else max(1, c-1)
                    return [c] + [gr.update(visible=(i < c)) for i in range(MAX_ROLES)]
                add_btn.click(up, [v_count, gr.State("add")], [v_count] + role_rows)
                rem_btn.click(up, [v_count, gr.State("remove")], [v_count] + role_rows)
        out = gr.Audio(label="成品下载", type="filepath")
        btn.click(run_tts, [txt, speed, dv] + role_inputs, out)

    with gr.Tab("🎙️ 听说对练"):
        mic = gr.Audio(sources="microphone", type="filepath", label="你的录音")
        res = gr.Textbox(label="AI 识别结果")
        def rec(audio):
            if not audio: return "无录音"
            c = speechsdk.SpeechConfig(SPEECH_KEY, SPEECH_REGION)
            c.speech_recognition_language = "de-DE"
            return speechsdk.SpeechRecognizer(c, speechsdk.AudioConfig(filename=audio)).recognize_once_async().get().text
        gr.Button("🔍 识别并纠错").click(rec, mic, res)

app.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 10000)))
