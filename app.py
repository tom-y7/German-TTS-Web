import gradio as gr
import azure.cognitiveservices.speech as speechsdk
import asyncio
import os
import re
import hashlib

# 1. 配置与初始化
SPEECH_KEY = os.environ.get("SPEECH_KEY")
SPEECH_REGION = os.environ.get("SPEECH_REGION")

# 创建智能缓存文件夹 (Render 重启时会自动清理，不用担心硬盘占满)
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

# 2. 核心：带“智能缓存”和“语速调节”的底层合成函数
def synthesize_with_cache(text, voice_id, speed_percent):
    # 计算这句话的专属数字指纹 (文本+音色+语速)
    hash_str = f"{text}_{voice_id}_{speed_percent}"
    file_hash = hashlib.md5(hash_str.encode('utf-8')).hexdigest()
    output_path = os.path.join(CACHE_DIR, f"{file_hash}.mp3")
    
    # 命中缓存：如果文件已经存在，直接白嫖本地文件，不消耗 Azure 额度！
    if os.path.exists(output_path):
        return output_path
        
    if not SPEECH_KEY or not SPEECH_REGION:
        raise gr.Error("系统未配置 Azure API Key！请在云平台环境变量中设置 SPEECH_KEY 和 SPEECH_REGION。")

    # 构建 SSML 以支持语速调节
    speed_str = f"{speed_percent}%" if speed_percent <= 0 else f"+{speed_percent}%"
    ssml = f"""
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="de-DE">
        <voice name="{voice_id}">
            <prosody rate="{speed_str}">{text}</prosody>
        </voice>
    </speak>
    """
    
    # 调用 Azure 官方接口
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    result = synthesizer.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise gr.Error(f"合成失败，微软接口返回: {result.reason}")
        
    return output_path

# 3. 高并发拼接调度器
async def generate_audio(script_text, speed, default_voice, r1_name, r1_voice, r2_name, r2_voice):
    if not script_text.strip():
        raise gr.Error("请输入要合成的文本！")
        
    mapping = {}
    for name, voice in [(r1_name, r1_voice), (r2_name, r2_voice)]:
        if name.strip():
            mapping[name.strip().lower()] = VOICE_OPTIONS[voice]
            
    def_voice_id = VOICE_OPTIONS[default_voice]
    lines = script_text.strip().split('\n')
    temp_files = [None] * len(lines)
    
    async def process_line(index, line):
        if not line.strip(): return
        match = re.match(r'^([^:：]+)[:：](.+)$', line.strip())
        if match:
            role, content = match.group(1).strip().lower(), match.group(2).strip()
            voice = mapping.get(role, def_voice_id)
        else:
            content, voice = line.strip(), def_voice_id
            
        # 将耗时的网络请求放入异步线程池
        path = await asyncio.to_thread(synthesize_with_cache, content, voice, speed)
        temp_files[index] = path

    # 十线程全开并发下载/调取缓存
    await asyncio.gather(*(process_line(i, line) for i, line in enumerate(lines)))
    
    # 无缝拼接
    final_path = os.path.join(CACHE_DIR, f"final_output_{hashlib.md5(script_text.encode('utf-8')).hexdigest()[:8]}.mp3")
    with open(final_path, 'wb') as outfile:
        for path in temp_files:
            if path and os.path.exists(path):
                with open(path, 'rb') as infile:
                    outfile.write(infile.read())
                    
    return final_path

# 4. 角色试听专用功能
def audition_voice(voice_name):
    voice_id = VOICE_OPTIONS[voice_name]
    # 从选项名字里截取人物名，比如 Katja
    name = voice_name.split(' ')[1] 
    test_text = f"Hallo, ich bin {name}. Schön, dich kennenzulernen!"
    # 试听一律使用正常语速(0%)
    return synthesize_with_cache(test_text, voice_id, 0)

# --- 5. 炫酷的前端 UI 搭建 ---
with gr.Blocks(theme=gr.themes.Soft(primary_hue="green")) as app:
    gr.Markdown("### 🎧 德语剧本配音引擎 (Pro 极客版)")
    
    with gr.Row():
        with gr.Column(scale=2):
            script_input = gr.Textbox(lines=10, placeholder="输入德语文本...\n\n旁白描述...\nSophie: Ich koche gern vegetarisch.\nTom: Das ist toll!", label="📝 剧本输入区")
            
            # 语速调节滑块
            speed_slider = gr.Slider(minimum=-50, maximum=20, value=0, step=5, label="⏱️ 语速调节 (%)", info="负数代表减速 (如 -20% 适合初学者跟读)，正数代表加速。")
            
            with gr.Accordion("🎭 角色分配面板 (附带试听功能)", open=True):
                with gr.Row():
                    default_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[2], label="[默认/旁白] 音色", scale=3)
                    btn_test_def = gr.Button("🎧 试听", scale=1, size="sm")
                
                gr.Markdown("---")
                with gr.Row():
                    r1_name = gr.Textbox(label="角色 1 名字", scale=1)
                    r1_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[0], label="角色 1 音色", scale=2)
                    btn_test_r1 = gr.Button("🎧 试听", scale=1, size="sm")
                with gr.Row():
                    r2_name = gr.Textbox(label="角色 2 名字", scale=1)
                    r2_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[1], label="角色 2 音色", scale=2)
                    btn_test_r2 = gr.Button("🎧 试听", scale=1, size="sm")
                    
            generate_btn = gr.Button("🚀 立即生成高音质 MP3", variant="primary", size="lg")
            
        with gr.Column(scale=1):
            # autoplay=False 完美禁用自动播放防打扰
            audio_output = gr.Audio(label="✅ 生成 / 试听结果", type="filepath", interactive=False, autoplay=False)
            
            gr.Markdown("""
            **💡 极客版特性说明:**
            1. **智能缓存**: 修改错别字重新生成时，未修改的句子会直接秒读取缓存，不耗时也不扣微软额度。
            2. **SSML语速**: 调节滑块后，底层自动构建 XML 标记请求微软引擎。
            """)

    # 绑定生成按钮
    generate_btn.click(
        fn=generate_audio, 
        inputs=[script_input, speed_slider, default_voice, r1_name, r1_voice, r2_name, r2_voice], 
        outputs=audio_output
    )
    # 绑定试听按钮
    btn_test_def.click(fn=audition_voice, inputs=[default_voice], outputs=audio_output)
    btn_test_r1.click(fn=audition_voice, inputs=[r1_voice], outputs=audio_output)
    btn_test_r2.click(fn=audition_voice, inputs=[r2_voice], outputs=audio_output)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.launch(server_name="0.0.0.0", server_port=port)
