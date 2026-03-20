import gradio as gr
import azure.cognitiveservices.speech as speechsdk
import asyncio
import os
import re
import tempfile

# 检查是否配置了官方秘钥（千万不要把秘钥直接写在代码里！）
SPEECH_KEY = os.environ.get("SPEECH_KEY")
SPEECH_REGION = os.environ.get("SPEECH_REGION")

# 微软官方德语音色库 (音色代号和之前一模一样)
VOICE_OPTIONS = {
    "👱‍♀️ Katja (标准青年女声)": "de-DE-KatjaNeural",
    "👨 Killian (标准青年男声)": "de-DE-KillianNeural",
    "👨‍💼 Conrad (浑厚新闻男声)": "de-DE-ConradNeural",
    "👩‍🦰 Seraphina (温柔知性女声)": "de-DE-SeraphinaNeural",
    "👦 Kasper (调皮小男孩)": "de-DE-KasperNeural",
    "👧 Maja (可爱小女孩)": "de-DE-MajaNeural"
}
VOICE_NAMES = list(VOICE_OPTIONS.keys())

# 调用官方 SDK 合成单句音频
def synthesize_single_line(text, voice_id, output_path):
    # 配置你的微软通行证
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_config.speech_synthesis_voice_name = voice_id
    # 设置输出格式为 MP3
    speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
    
    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    # 执行合成
    result = synthesizer.speak_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise gr.Error(f"合成失败，微软接口返回: {result.reason}")

# 核心异步高并发合并逻辑
async def generate_audio(script_text, default_voice, r1_name, r1_voice, r2_name, r2_voice):
    if not SPEECH_KEY or not SPEECH_REGION:
        raise gr.Error("系统未配置 Azure API Key！请在云平台环境变量中设置 SPEECH_KEY 和 SPEECH_REGION。")
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
            
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        temp_files[index] = path
        
        # 将官方的同步接口放入异步线程池，实现高并发
        await asyncio.to_thread(synthesize_single_line, content, voice, path)

    # 启动并发引擎
    await asyncio.gather(*(process_line(i, line) for i, line in enumerate(lines)))
    
    # 拼接音频
    fd, final_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    with open(final_path, 'wb') as outfile:
        for path in temp_files:
            if path and os.path.exists(path):
                with open(path, 'rb') as infile:
                    outfile.write(infile.read())
                os.remove(path)
                
    return final_path

# --- UI 界面 (为了精简演示，保留两个自定义角色位，你可以随时加回四个) ---
with gr.Blocks(theme=gr.themes.Soft(primary_hue="green")) as app:
    gr.Markdown("### 🎧 德语剧本配音引擎 (Azure 官方直连版)")
    script_input = gr.Textbox(lines=8, placeholder="输入德语文本...", label="📝 剧本输入区")
    
    with gr.Accordion("🎭 角色分配面板", open=True):
        default_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[2], label="[默认/旁白] 音色")
        with gr.Row():
            r1_name = gr.Textbox(label="角色 1 名字", scale=1)
            r1_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[0], label="角色 1 音色", scale=2)
        with gr.Row():
            r2_name = gr.Textbox(label="角色 2 名字", scale=1)
            r2_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[1], label="角色 2 音色", scale=2)
            
    generate_btn = gr.Button("🚀 调用官方 API 生成", variant="primary")
    audio_output = gr.Audio(label="生成结果", type="filepath")
    generate_btn.click(fn=generate_audio, inputs=[script_input, default_voice, r1_name, r1_voice, r2_name, r2_voice], outputs=audio_output)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.launch(server_name="0.0.0.0", server_port=port)
