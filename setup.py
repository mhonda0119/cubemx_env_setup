import json
import os
import shutil
import urllib.request
import re
import subprocess
from pathlib import Path

# ==========================================
# 設定
# ==========================================
CONFIG_FILE = "setup_config.json"

SEGGER_RTT_BASE_URL = "https://raw.githubusercontent.com/SEGGERMicro/RTT/main/RTT"
SVD_BASE_URL = "https://raw.githubusercontent.com/posborne/cmsis-svd/master/data/STMicro"

# ==========================================
# ユーティリティ関数
# ==========================================
def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"[{CONFIG_FILE}] が見つかりません。")
        exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def download_file(url, dest_path):
    print(f"ダウンロード中: {url} -> {dest_path}")
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f"ダウンロード成功: {dest_path}")
    except Exception as e:
        print(f"ダウンロード失敗: {url}\nエラー: {e}")

def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"ディレクトリ作成: {path}")

def replace_in_file(file_path, pattern, replacement):
    if not os.path.exists(file_path):
        print(f"ファイルが見つかりません: {file_path}")
        return
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    if content != new_content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"ファイル更新: {file_path}")

def get_project_and_device():
    project_name = "unknown_project"
    device = "STM32F405RG"
    
    # 1. CMakeLists.txt から project_name を取得
    if os.path.exists("CMakeLists.txt"):
        with open("CMakeLists.txt", "r", encoding="utf-8") as f:
            match = re.search(r'set\(\s*CMAKE_PROJECT_NAME\s+([^\s\)]+)\s*\)', f.read(), re.IGNORECASE)
            if match:
                project_name = match.group(1)
                
    # 2. .ioc ファイルから device を取得
    ioc_files = [f for f in os.listdir(".") if f.endswith(".ioc")]
    if ioc_files:
        with open(ioc_files[0], "r", encoding="utf-8") as f:
            match = re.search(r'Mcu\.UserName=(STM32[^\s]+)', f.read())
            if match:
                mcu_name = match.group(1)
                # J-Link用のDevice名（パッケージ文字などを除いた先頭11文字）
                # 例: STM32F405RGTx -> STM32F405RG
                # 例: STM32G431KBUx -> STM32G431KB
                device = mcu_name[:11]
                
    return project_name, device

# ==========================================
# メイン処理
# ==========================================
def main():
    config = load_config()
    
    # プロジェクト名とデバイス名を自動取得
    project_name, device = get_project_and_device()
    
    # 設定値を取得
    c_standard = config["language"]["c_standard"]
    cpp_standard = config["language"]["cpp_standard"]
    cpp_ext = config["language"]["cpp_extension"]
    
    jlink_exe = config["toolchain"]["jlink_exe"]
    jlink_gdb_server = config["toolchain"]["jlink_gdb_server"]
    arm_toolchain_path = config["toolchain"]["gcc_path"]
    ninja_path = config["toolchain"]["ninja_path"]

    print(f"\n=== プロジェクト設定 ===")
    print(f"プロジェクト名: {project_name}")
    print(f"デバイス: {device}")
    print(f"C標準: C{c_standard}")
    print(f"C++標準: C++{cpp_standard}")
    print(f"C++拡張子: {cpp_ext}")

    # 1. フォルダ構成作成
    print("\n--- 1. フォルダ構成作成 ---")
    create_dir("apps/src")
    create_dir("apps/inc")
    create_dir("libs/segger_rtt/src")
    create_dir("libs/segger_rtt/inc")
    create_dir("Device/svd")
    create_dir(".vscode")

    # 2. main.c -> main.cc 移動（既存のmain.ccがある場合はスキップ）
    print("\n--- 2. main.c の移動 ---")
    src_main_c = "Core/Src/main.c"
    dest_main_cc = f"apps/src/main{cpp_ext}"
    
    if os.path.exists(dest_main_cc):
        print(f"✓ {dest_main_cc} は既に存在するためスキップします。")
    elif os.path.exists(src_main_c):
        shutil.move(src_main_c, dest_main_cc)
        print(f"✓ {src_main_c} を {dest_main_cc} に移動しました。")
    else:
        print(f"⚠ {src_main_c} が見つかりません。")

    src_main_h = "Core/Inc/main.h"
    dest_main_h = "apps/inc/main.h"
    if os.path.exists(src_main_h) and not os.path.exists(dest_main_h):
        shutil.move(src_main_h, dest_main_h)
        print(f"✓ {src_main_h} を {dest_main_h} に移動しました。")
    elif os.path.exists(dest_main_h):
        print(f"✓ {dest_main_h} は既に存在します。")

    # 3. SEGGER RTT ダウンロード
    print("\n--- 3. SEGGER RTT ダウンロード ---")
    rtt_files = {
        f"{SEGGER_RTT_BASE_URL}/SEGGER_RTT.c": "libs/segger_rtt/src/SEGGER_RTT.c",
        f"{SEGGER_RTT_BASE_URL}/SEGGER_RTT_printf.c": "libs/segger_rtt/src/SEGGER_RTT_printf.c",
        f"{SEGGER_RTT_BASE_URL}/SEGGER_RTT.h": "libs/segger_rtt/inc/SEGGER_RTT.h",
        "https://raw.githubusercontent.com/SEGGERMicro/RTT/main/Config/SEGGER_RTT_Conf.h": "libs/segger_rtt/inc/SEGGER_RTT_Conf.h"
    }
    for url, dest in rtt_files.items():
        if not os.path.exists(dest):
            download_file(url, dest)
        else:
            print(f"✓ {dest} は既に存在します。")

    # 4. SVD ダウンロード
    print("\n--- 4. SVD ダウンロード ---")
    match = re.search(r'(STM32F\d{3})', device)
    if match:
        svd_base = match.group(1)
        svd_url = f"{SVD_BASE_URL}/{svd_base}.svd"
        dest_svd = f"Device/svd/{svd_base}.svd"
        if not os.path.exists(dest_svd):
            download_file(svd_url, dest_svd)
        else:
            print(f"✓ {dest_svd} は既に存在します。")
    else:
        print(f"⚠ SVDベース名の抽出に失敗しました: {device}")

    # 5. CMakeLists.txt (root) 編集
    print("\n--- 5. CMakeLists.txt (root) 編集 ---")
    root_cmake = "CMakeLists.txt"
    if os.path.exists(root_cmake):
        with open(root_cmake, "r", encoding="utf-8") as f:
            content = f.read()

        modified = False

        # C標準の設定を更新
        if f"set(CMAKE_C_STANDARD {c_standard})" not in content:
            content = re.sub(r'set\(CMAKE_C_STANDARD \d+\)', f'set(CMAKE_C_STANDARD {c_standard})', content)
            modified = True

        # C++標準の設定を追加または更新
        if "set(CMAKE_CXX_STANDARD" not in content:
            cxx_setup = f"""
#--------------追記(開始)--------------
# C++ settings
set(CMAKE_CXX_STANDARD {cpp_standard}) # C++{cpp_standard}の有効化
set(CMAKE_CXX_STANDARD_REQUIRED ON) # C++{cpp_standard}を必須にする
set(CMAKE_CXX_EXTENSIONS OFF) # C++標準のみを使用する
#--------------追記(終了)--------------
"""
            content = re.sub(r'(set\(CMAKE_C_EXTENSIONS ON\))', r'\1\n' + cxx_setup, content, count=1)
            modified = True
        else:
            # 既存のC++標準設定を更新
            content = re.sub(r'set\(CMAKE_CXX_STANDARD \d+\)', f'set(CMAKE_CXX_STANDARD {cpp_standard})', content)
            modified = True

        # enable_language に CXX を追加
        if "enable_language(C CXX ASM)" not in content:
            content = re.sub(r'enable_language\(C ASM\)', 'enable_language(C CXX ASM)', content)
            modified = True

        # app_src と libs_src の設定を追加
        if "file(GLOB_RECURSE app_src" not in content:
            app_libs_block = f"""
#-------------追記(開始)--------------
file(GLOB_RECURSE app_src
    "apps/src/*{cpp_ext}"
    "apps/src/*.c"
)
file(GLOB_RECURSE libs_src
    "libs/*{cpp_ext}"
    "libs/*.c"
)

file(GLOB app_inc_dirs
  "${{CMAKE_SOURCE_DIR}}/apps/inc"
)
file(GLOB libs_inc_dirs
  "${{CMAKE_SOURCE_DIR}}/libs/*/inc"
)
#--------------追記(終了)--------------
"""
            content = content.replace("target_sources(${CMAKE_PROJECT_NAME} PRIVATE", app_libs_block + "\ntarget_sources(${CMAKE_PROJECT_NAME} PRIVATE")
            modified = True

        # target_sources に追加
        if "${app_src}" not in content:
            content = re.sub(
                r'(target_sources\(\$\{CMAKE_PROJECT_NAME\} PRIVATE\s*# Add user sources here)',
                r'\1\n\n    ${app_src}\n    ${libs_src}',
                content
            )
            modified = True

        # target_include_directories に追加
        if "${app_inc_dirs}" not in content:
            content = re.sub(
                r'(target_include_directories\(\$\{CMAKE_PROJECT_NAME\} PRIVATE\s*# Add user defined include paths)',
                r'\1\n\n    ${app_inc_dirs}\n    ${libs_inc_dirs}',
                content
            )
            modified = True

        # libob.a 依存関係の削除
        if "list(REMOVE_ITEM CMAKE_C_IMPLICIT_LINK_LIBRARIES ob)" not in content:
            content = content.rstrip() + "\n\n# Remove wrong libob.a library dependency when using cpp files\nlist(REMOVE_ITEM CMAKE_C_IMPLICIT_LINK_LIBRARIES ob)\n"
            modified = True

        if modified:
            with open(root_cmake, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✓ {root_cmake} を更新しました。")
        else:
            print(f"✓ {root_cmake} は既に設定済みです。")

    # 6. cmake/stm32cubemx/CMakeLists.txt 編集
    print("\n--- 6. cmake/stm32cubemx/CMakeLists.txt 編集 ---")
    cube_cmake = "cmake/stm32cubemx/CMakeLists.txt"
    if os.path.exists(cube_cmake):
        with open(cube_cmake, "r", encoding="utf-8") as f:
            content = f.read()
        
        # main.c の行をコメントアウト
        if re.search(r'^\s*\$\{CMAKE_CURRENT_SOURCE_DIR\}/\.\./\.\./Core/Src/main\.c', content, re.MULTILINE):
            content = re.sub(
                r'^(\s*)(\$\{CMAKE_CURRENT_SOURCE_DIR\}/\.\./\.\./Core/Src/main\.c)',
                r'\1#\2',
                content,
                flags=re.MULTILINE
            )
            with open(cube_cmake, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✓ {cube_cmake} を更新しました（main.cをコメントアウト）。")
        else:
            print(f"✓ {cube_cmake} は既に設定済みです。")

    # 7. CMakePresets.json 編集
    print("\n--- 7. CMakePresets.json 編集 ---")
    presets_file = "CMakePresets.json"
    if os.path.exists(presets_file):
        with open(presets_file, "r", encoding="utf-8") as f:
            presets = json.load(f)

        modified = False

        # default preset の環境変数を更新
        for preset in presets.get("configurePresets", []):
            if preset.get("name") == "default":
                if "environment" not in preset:
                    preset["environment"] = {}
                preset["environment"]["PATH"] = f"{ninja_path};{arm_toolchain_path};$penv{{PATH}}"
                modified = True

        # Release preset の追加
        has_release_config = any(p.get("name") == "Release" for p in presets.get("configurePresets", []))
        if not has_release_config:
            presets["configurePresets"].append({
                "name": "Release",
                "inherits": "default",
                "cacheVariables": {
                    "CMAKE_BUILD_TYPE": "Release"
                }
            })
            modified = True

        has_release_build = any(p.get("name") == "Release" for p in presets.get("buildPresets", []))
        if not has_release_build:
            if "buildPresets" not in presets:
                presets["buildPresets"] = []
            presets["buildPresets"].append({
                "name": "Release",
                "configurePreset": "Release"
            })
            modified = True

        if modified:
            with open(presets_file, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=4)
            print(f"✓ {presets_file} を更新しました。")
        else:
            print(f"✓ {presets_file} は既に設定済みです。")

    # 8. .clangd 生成（Debugのみ対応）
    print("\n--- 8. .clangd 生成 ---")
    clangd_content = """CompileFlags:
  CompilationDatabase: build/Debug
InlayHints:
  Enabled: Yes
  ParameterNames: Yes
  DeducedTypes: No
  Designators: No
"""
    with open(".clangd", "w", encoding="utf-8") as f:
        f.write(clangd_content)
    print("✓ .clangd を生成しました（Debug専用設定）。")

    # 9. .vscode/launch.json 生成
    print("\n--- 9. launch.json 生成 ---")
    jlink_server = jlink_gdb_server.replace('\\', '\\\\')
    arm_toolchain_escaped = arm_toolchain_path.replace('\\', '\\\\')
    
    svd_base = re.search(r'(STM32F\d{3})', device).group(1) if re.search(r'(STM32F\d{3})', device) else device
    svd_file_path = f"${{workspaceRoot}}/Device/svd/{svd_base}.svd"

    launch_json_content = f"""{{
    "version": "0.2.0",
    "configurations": [
        {{
            "name": "Cortex Debug (Debug)",
            "cwd": "${{workspaceRoot}}",
            "executable": "./build/Debug/{project_name}.elf",
            "request": "launch",
            "type": "cortex-debug",
            "servertype": "jlink",
            "device": "{device}",
            "interface": "swd",
            "serverpath": "{jlink_server}",
            "armToolchainPath": "{arm_toolchain_escaped}",
            "svdFile": "{svd_file_path}",
            "debuggerArgs": [
                "-iex",
                "set auto-load safe-path /"
            ],
            "runToEntryPoint": "main",
            "rttConfig": {{
                "enabled": true,
                "address": "auto",
                "decoders": [
                    {{
                        "port": 0,
                        "type": "console"
                    }}
                ]
            }}
        }},
        {{
            "name": "Cortex Debug (Release)",
            "cwd": "${{workspaceRoot}}",
            "executable": "./build/Release/{project_name}.elf",
            "request": "launch",
            "type": "cortex-debug",
            "servertype": "jlink",
            "device": "{device}",
            "interface": "swd",
            "serverpath": "{jlink_server}",
            "armToolchainPath": "{arm_toolchain_escaped}",
            "svdFile": "{svd_file_path}",
            "debuggerArgs": [
                "-iex",
                "set auto-load safe-path /"
            ],
            "runToEntryPoint": "main"
        }}
    ]
}}
"""
    with open(".vscode/launch.json", "w", encoding="utf-8") as f:
        f.write(launch_json_content)
    print("✓ .vscode/launch.json を生成しました。")

    # 10. .vscode/tasks.json 生成（全パターン対応）
    print("\n--- 10. tasks.json 生成 ---")
    tasks_json_content = f"""{{
  "version": "2.0.0",
  "tasks": [
    {{
      "label": "Configure Debug",
      "type": "shell",
      "command": "cmake",
      "args": ["--preset", "Debug", "--fresh"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Configure Release",
      "type": "shell",
      "command": "cmake",
      "args": ["--preset", "Release", "--fresh"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Build Debug",
      "type": "shell",
      "command": "cmake",
      "args": ["--build", "--preset", "Debug"],
      "group": "build",
      "problemMatcher": ["$gcc"]
    }},
    {{
      "label": "Build Release",
      "type": "shell",
      "command": "cmake",
      "args": ["--build", "--preset", "Release"],
      "group": "build",
      "problemMatcher": ["$gcc"]
    }},
    {{
      "label": "Configure & Build Debug",
      "dependsOrder": "sequence",
      "dependsOn": ["Configure Debug", "Build Debug"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Configure & Build Release",
      "dependsOrder": "sequence",
      "dependsOn": ["Configure Release", "Build Release"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Flash Debug",
      "type": "shell",
      "command": "& '{jlink_exe}' -device {device} -CommanderScript '${{workspaceFolder}}/.vscode/Run_Flash_Debug.jlink'",
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Flash Release",
      "type": "shell",
      "command": "& '{jlink_exe}' -device {device} -CommanderScript '${{workspaceFolder}}/.vscode/Run_Flash_Release.jlink'",
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Build & Flash Debug",
      "dependsOrder": "sequence",
      "dependsOn": ["Build Debug", "Flash Debug"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Build & Flash Release",
      "dependsOrder": "sequence",
      "dependsOn": ["Build Release", "Flash Release"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Configure & Build & Flash Debug",
      "dependsOrder": "sequence",
      "dependsOn": ["Configure Debug", "Build Debug", "Flash Debug"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Configure & Build & Flash Release",
      "dependsOrder": "sequence",
      "dependsOn": ["Configure Release", "Build Release", "Flash Release"],
      "group": "build",
      "problemMatcher": []
    }},
    {{
      "label": "Erase Flash",
      "type": "shell",
      "command": "& '{jlink_exe}' -device {device} -CommanderScript '${{workspaceFolder}}/.vscode/Run_Erase_Flash.jlink'",
      "group": "build",
      "problemMatcher": []
    }}
  ]
}}
"""
    with open(".vscode/tasks.json", "w", encoding="utf-8") as f:
        f.write(tasks_json_content)
    print("✓ .vscode/tasks.json を生成しました（全パターン対応）。")

    # 11. .jlink スクリプト生成
    print("\n--- 11. .jlink スクリプト生成 ---")
    jlink_debug = f"""// Connect
si SWD
speed 4000
r

// Halt, program ELF, verify
h
loadfile ./build/Debug/{project_name}.elf
verify

// Reset & run
r
g
qc
"""
    with open(".vscode/Run_Flash_Debug.jlink", "w", encoding="utf-8") as f:
        f.write(jlink_debug)

    jlink_release = f"""// Connect
si SWD
speed 4000
r

// Halt, program ELF, verify
h
loadfile ./build/Release/{project_name}.elf
verify

// Reset & run
r
g
qc
"""
    with open(".vscode/Run_Flash_Release.jlink", "w", encoding="utf-8") as f:
        f.write(jlink_release)

    jlink_erase = """si SWD
speed 4000
r
h

// Mass erase
erase

r
qc
"""
    with open(".vscode/Run_Erase_Flash.jlink", "w", encoding="utf-8") as f:
        f.write(jlink_erase)
    print("✓ *.jlink ファイルを生成しました。")

    print("\n" + "="*50)
    print("✓ セットアップ完了！")
    print("="*50)
    print("\n次のステップ:")
    print("1. VSCode のタスク (Ctrl+Shift+B) から 'Configure & Build Debug' を実行")
    print("2. ビルドが成功したら 'Flash Debug' でマイコンに書き込み")
    print("3. F5 キーでデバッグ開始")

if __name__ == "__main__":
    main()