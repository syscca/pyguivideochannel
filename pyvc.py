import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# 全局变量，存储分类结果
video_categories = {
    "左声道无声": [],
    "右声道无声": [],
    "单声道": [],
    "立体声": []
}

def detect_silent_channel(input_file):
    """
    检测哪个声道是无声的
    """
    # 使用ffmpeg拆分声道并检测音量
    command_left = [
        'ffmpeg',
        '-i', input_file,
        '-map', '0:a:0',  # 选择第一个音频流
        '-af', 'channelsplit=channel_layout=stereo[L][R]',  # 拆分为左右声道
        '-map', '[L]',  # 选择左声道
        '-af', 'volumedetect',  # 音量检测
        '-f', 'null', '/dev/null'  # 输出到空设备
    ]
    
    command_right = [
        'ffmpeg',
        '-i', input_file,
        '-map', '0:a:0',  # 选择第一个音频流
        '-af', 'channelsplit=channel_layout=stereo[L][R]',  # 拆分为左右声道
        '-map', '[R]',  # 选择右声道
        '-af', 'volumedetect',  # 音量检测
        '-f', 'null', '/dev/null'  # 输出到空设备
    ]
    
    try:
        # 检测左声道
        result_left = subprocess.run(command_left, stderr=subprocess.PIPE, encoding='utf-8', errors='ignore')
        output_left = result_left.stderr
        
        # 检测右声道
        result_right = subprocess.run(command_right, stderr=subprocess.PIPE, encoding='utf-8', errors='ignore')
        output_right = result_right.stderr
        
        # 分析左声道音量
        if "mean_volume: -inf" in output_left:
            left_silent = True
        else:
            left_silent = False
        
        # 分析右声道音量
        if "mean_volume: -inf" in output_right:
            right_silent = True
        else:
            right_silent = False
        
        # 返回检测结果
        if left_silent and not right_silent:
            return "左声道无声"
        elif right_silent and not left_silent:
            return "右声道无声"
        elif left_silent and right_silent:
            return "单声道"
        else:
            return "立体声"
    except subprocess.CalledProcessError as e:
        return f"检测声道时出错: {e}"

def process_video(input_file, output_file, active_channel):
    """
    处理视频，将有声的声道复制到无声的声道
    """
    if active_channel == "左声道无声":
        # 右声道有声，复制到左声道
        pan_filter = 'pan=stereo|c0=c1|c1=c1'
    elif active_channel == "右声道无声":
        # 左声道有声，复制到右声道
        pan_filter = 'pan=stereo|c0=c0|c1=c0'
    else:
        return  # 无需处理
    
    # 使用英特尔QSV硬件加速（如果支持）
    command = [
        'ffmpeg',
        '-i', input_file,
        '-map', '0:v',  # 复制视频流
        '-c:v', 'h264_qsv',  # 使用QSV硬件加速
        '-map', '0:a',  # 处理音频流
        '-af', pan_filter,  # 应用声道复制
        '-c:a', 'aac',  # 重新编码音频
        output_file
    ]
    
    try:
        subprocess.run(command, check=True, encoding='utf-8', errors='ignore')
    except subprocess.CalledProcessError as e:
        # 如果QSV不支持，回退到软件编码
        command[6] = 'copy'  # 将视频流改为直接复制
        try:
            subprocess.run(command, check=True, encoding='utf-8', errors='ignore')
        except subprocess.CalledProcessError as e:
            raise Exception(f"处理视频时出错: {e}")

def select_input_file():
    file_path = filedialog.askopenfilename(
        title="选择视频文件",
        filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov")]
    )
    if file_path:
        input_file_entry.delete(0, tk.END)
        input_file_entry.insert(0, file_path)

def select_input_directory():
    directory = filedialog.askdirectory(title="选择目录")
    if directory:
        input_directory_entry.delete(0, tk.END)
        input_directory_entry.insert(0, directory)

def find_video_files(directory):
    """
    递归查找目录下的所有视频文件
    """
    video_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')):
                video_files.append(os.path.join(root, file))
    return video_files

def update_category_tree():
    """
    更新分类结果表格
    """
    # 清空表格
    for row in category_tree.get_children():
        category_tree.delete(row)
    
    # 插入新的分类结果
    for category, files in video_categories.items():
        category_tree.insert("", "end", values=(category, len(files)))

def start_single_detection():
    input_file = input_file_entry.get()
    if not input_file:
        messagebox.showwarning("警告", "请选择视频文件！")
        return
    
    # 清空检测结果
    detection_result_text.delete(1.0, tk.END)
    for category in video_categories:
        video_categories[category].clear()
    
    # 检测声道状态
    result = detect_silent_channel(input_file)
    if result in video_categories:
        video_categories[result].append(input_file)
    detection_result_text.insert(tk.END, f"{os.path.basename(input_file)}: {result}\n")
    
    # 更新分类结果表格
    update_category_tree()
    messagebox.showinfo("完成", "单文件检测完成！")

def start_single_processing():
    input_file = input_file_entry.get()
    if not input_file:
        messagebox.showwarning("警告", "请选择视频文件！")
        return
    
    # 获取分类结果
    result = None
    for category, files in video_categories.items():
        if input_file in files:
            result = category
            break
    
    if not result:
        messagebox.showwarning("警告", "请先检测视频文件！")
        return
    
    # 生成输出文件名
    output_file = os.path.splitext(input_file)[0] + "_fixed.mp4"
    
    # 处理视频
    try:
        process_video(input_file, output_file, result)
        detection_result_text.insert(tk.END, f"{os.path.basename(input_file)}: 处理完成 -> {output_file}\n")
        messagebox.showinfo("完成", "单文件处理完成！")
    except Exception as e:
        detection_result_text.insert(tk.END, f"{os.path.basename(input_file)}: 处理失败 -> {str(e)}\n")
        messagebox.showerror("错误", f"处理视频时出错: {e}")

def start_batch_detection():
    directory = input_directory_entry.get()
    if not directory:
        messagebox.showwarning("警告", "请选择目录！")
        return
    
    # 清空检测结果
    detection_result_text.delete(1.0, tk.END)
    for category in video_categories:
        video_categories[category].clear()
    
    # 查找所有视频文件
    video_files = find_video_files(directory)
    if not video_files:
        messagebox.showwarning("警告", "未找到视频文件！")
        return
    
    # 在子线程中批量检测声道，避免界面卡死
    def run_batch_detection():
        for video_file in video_files:
            result = detect_silent_channel(video_file)
            if result in video_categories:
                video_categories[result].append(video_file)
            detection_result_text.insert(tk.END, f"{os.path.basename(video_file)}: {result}\n")
        
        # 更新分类结果表格
        update_category_tree()
        messagebox.showinfo("完成", "批量检测完成！")
    
    detection_thread = threading.Thread(target=run_batch_detection)
    detection_thread.start()

def start_batch_processing():
    # 获取用户选择的分类
    selected_categories = []
    for category, var in category_vars.items():
        if var.get():
            selected_categories.append(category)
    
    if not selected_categories:
        messagebox.showwarning("警告", "请选择至少一个分类！")
        return
    
    # 获取需要处理的文件
    files_to_process = []
    for category in selected_categories:
        files_to_process.extend(video_categories[category])
    
    if not files_to_process:
        messagebox.showwarning("警告", "未找到需要处理的文件！")
        return
    
    # 在子线程中批量处理视频，避免界面卡死
    def run_batch_processing():
        for video_file in files_to_process:
            try:
                # 获取分类结果
                result = None
                for category, files in video_categories.items():
                    if video_file in files:
                        result = category
                        break
                
                if not result:
                    continue
                
                # 生成输出文件名
                output_file = os.path.splitext(video_file)[0] + "_fixed.mp4"
                
                # 处理视频
                process_video(video_file, output_file, result)
                detection_result_text.insert(tk.END, f"{os.path.basename(video_file)}: 处理完成 -> {output_file}\n")
            except Exception as e:
                detection_result_text.insert(tk.END, f"{os.path.basename(video_file)}: 处理失败 -> {str(e)}\n")
        
        messagebox.showinfo("完成", "批量处理完成！")
    
    processing_thread = threading.Thread(target=run_batch_processing)
    processing_thread.start()

# 创建主窗口
root = tk.Tk()
root.title("视频声道检测与处理工具")

# 设置窗口最小大小
root.minsize(600, 400)

# 配置网格布局权重
root.columnconfigure(1, weight=1)
root.rowconfigure(4, weight=1)

# 单文件操作区域
single_file_frame = ttk.LabelFrame(root, text="单文件操作")
single_file_frame.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

input_file_label = tk.Label(single_file_frame, text="选择视频文件:")
input_file_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

input_file_entry = tk.Entry(single_file_frame, width=50)
input_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

input_file_button = tk.Button(single_file_frame, text="浏览", command=select_input_file)
input_file_button.grid(row=0, column=2, padx=5, pady=5, sticky="e")

detect_single_button = tk.Button(single_file_frame, text="检测声道", command=start_single_detection)
detect_single_button.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

process_single_button = tk.Button(single_file_frame, text="处理视频", command=start_single_processing)
process_single_button.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

# 批量操作区域
batch_file_frame = ttk.LabelFrame(root, text="批量操作")
batch_file_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

input_directory_label = tk.Label(batch_file_frame, text="选择目录:")
input_directory_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

input_directory_entry = tk.Entry(batch_file_frame, width=50)
input_directory_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

input_directory_button = tk.Button(batch_file_frame, text="浏览", command=select_input_directory)
input_directory_button.grid(row=0, column=2, padx=5, pady=5, sticky="e")

detect_batch_button = tk.Button(batch_file_frame, text="批量检测声道", command=start_batch_detection)
detect_batch_button.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

process_batch_button = tk.Button(batch_file_frame, text="批量处理视频", command=start_batch_processing)
process_batch_button.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

# 分类结果归纳框
category_frame = ttk.LabelFrame(root, text="分类结果")
category_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

# 创建分类结果表格
category_tree = ttk.Treeview(category_frame, columns=("分类", "文件数量"), show="headings", height=5)
category_tree.heading("分类", text="分类")
category_tree.heading("文件数量", text="文件数量")
category_tree.column("分类", width=150)
category_tree.column("文件数量", width=100)
category_tree.pack(fill="both", expand=True)

# 分类选择
category_select_frame = ttk.LabelFrame(root, text="选择需要处理的分类")
category_select_frame.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

category_vars = {}
for i, category in enumerate(video_categories.keys()):
    category_vars[category] = tk.BooleanVar()
    checkbox = ttk.Checkbutton(category_select_frame, text=category, variable=category_vars[category])
    checkbox.grid(row=0, column=i, padx=5, pady=5, sticky="w")

# 检测结果显示
detection_result_text = scrolledtext.ScrolledText(root, width=60, height=15)
detection_result_text.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

# 运行主循环
root.mainloop()
