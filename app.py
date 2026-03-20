import gradio as gr
import edge_tts
import asyncio
import os
import re
import tempfile

# 微软 edge-tts 核心德语音色库
VOICE_OPTIONS = {
    "👱‍♀️ Katja (标准青年女声)": "de-DE-KatjaNeural",
    "👨 Killian (标准青年男声)": "de-DE-KillianNeural",
    "👩 Amala (活泼年轻女声)": "de-DE-AmalaNeural",
    "👨‍💼 Conrad (浑厚新闻男声)": "de-DE-ConradNeural",
    "👩‍🦰 Seraphina (温柔知性女声)": "de-DE-SeraphinaNeural",
    "👦 Kasper (调皮小男孩)": "de-DE-KasperNeural",
    "👧 Maja (可爱小女孩)": "de-DE-MajaNeural",
    "🇦🇹 Ingrid (奥地利女声)": "de-AT-IngridNeural",
    "🇦🇹 Jonas (奥地利男声)": "de-AT-JonasNeural",
    "🇨🇭 Leni (瑞士女声)": "de-CH-LeniNeural",
    "🇨🇭 Jan (瑞士男声)": "de-CH-JanNeural"
}
VOICE_NAMES = list(VOICE_OPTIONS.keys())

# 核心异步高并发合成逻辑
async def generate_audio(script_text, default_voice, r1_name, r1_voice, r2_name, r2_voice, r3_name, r3_voice, r4_name, r4_voice):
    if not script_text.strip():
        raise gr.Error("请输入要合成的文本！")
        
    # 1. 构建角色映射字典
    mapping = {}
    roles_input = [(r1_name, r1_voice), (r2_name, r2_voice), (r3_name, r3_voice), (r4_name, r4_voice)]
    for name, voice in roles_input:
        if name.strip():
            mapping[name.strip().lower()] = VOICE_OPTIONS[voice]
            
    def_voice_id = VOICE_OPTIONS[default_voice]
    
    # 2. 解析文本并准备临时文件
    lines = script_text.strip().split('\n')
    temp_files = [None] * len(lines)
    semaphore = asyncio.Semaphore(10) # 限制最高 10 并发
    
    async def process_line(index, line):
        if not line.strip(): return
        
        async with semaphore:
            # 正则解析 角色: 台词
            match = re.match(r'^([^:：]+)[:：](.+)$', line.strip())
            if match:
                role = match.group(1).strip().lower()
                content = match.group(2).strip()
                voice = mapping.get(role, def_voice_id)
            else:
                content = line.strip()
                voice = def_voice_id
                
            # 创建安全的临时文件路径
            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            temp_files[index] = path
            
            # 调用 edge-tts 生成
            comm = edge_tts.Communicate(content, voice)
            await comm.save(path)

    # 3. 启动高并发引擎
    tasks = [process_line(i, line) for i, line in enumerate(lines)]
    await asyncio.gather(*tasks)
    
    # 4. 按原始顺序拼接音频
    fd, final_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    
    with open(final_path, 'wb') as outfile:
        for path in temp_files:
            if path and os.path.exists(path):
                with open(path, 'rb') as infile:
                    outfile.write(infile.read())
                os.remove(path) # 阅后即焚清理内存
                
    return final_path

# --- 搭建炫酷的手机端响应式 Web UI ---
with gr.Blocks(theme=gr.themes.Soft(primary_hue="green")) as app:
    gr.Markdown("""
    # 🎧 德语剧本配音引擎 (Web 高并发版)
    输入带角色名的对话文本（例如 `Sophie: Hallo!`），系统会自动分配音色并合并为一个完美的 MP3 文件。
    """)
    
    with gr.Row():
        with gr.Column():
            # 文本输入区
            script_input = gr.Textbox(
                lines=10, 
                placeholder="在此输入德语文本...\n\n旁白描述...\nSophie: Ich koche gern vegetarisch.\nTom: Das ist toll!", 
                label="📝 剧本输入区"
            )
            
            # 折叠面板：角色分配（手机上为了省空间，默认折叠）
            with gr.Accordion("🎭 角色音色分配面板 (点击展开)", open=True):
                default_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[3], label="[旁白 / 未匹配角色] 默认音色")
                gr.Markdown("---")
                with gr.Row():
                    r1_name = gr.Textbox(label="角色 1 名字 (如: Sophie)", scale=1)
                    r1_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[0], label="角色 1 音色", scale=2)
                with gr.Row():
                    r2_name = gr.Textbox(label="角色 2 名字", scale=1)
                    r2_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[1], label="角色 2 音色", scale=2)
                with gr.Row():
                    r3_name = gr.Textbox(label="角色 3 名字", scale=1)
                    r3_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[5], label="角色 3 音色", scale=2)
                with gr.Row():
                    r4_name = gr.Textbox(label="角色 4 名字", scale=1)
                    r4_voice = gr.Dropdown(choices=VOICE_NAMES, value=VOICE_NAMES[6], label="角色 4 音色", scale=2)
                    
            generate_btn = gr.Button("🚀 一键并发合成音频", variant="primary", size="lg")
            
        with gr.Column():
            # 音频输出区
            audio_output = gr.Audio(label="✅ 生成结果 (可直接播放或点击右侧下载)", type="filepath", interactive=False)

    # 绑定按钮点击事件到核心逻辑
    generate_btn.click(
        fn=generate_audio,
        inputs=[script_input, default_voice, r1_name, r1_voice, r2_name, r2_voice, r3_name, r3_voice, r4_name, r4_voice],
        outputs=audio_output
    )

if __name__ == "__main__":
    import os
    # 获取云平台分配的端口，如果没有就默认用 10000
    port = int(os.environ.get("PORT", 10000))
    # 必须指定 0.0.0.0，否则外部无法访问
    app.launch(server_name="0.0.0.0", server_port=port)