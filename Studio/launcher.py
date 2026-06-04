"""
launcher.py — AutoToon Studio 启动器
选择不同的 UI 版本启动
"""
import sys
import dearpygui.dearpygui as dpg

VERSION = "v2.1.0"

UI_OPTIONS = [
    {"name": "Skybox v2.1 (Recommended)", "module": "ui_skybox", "desc": "Full featured: 6 shapes, 9 skyboxes, UE5, batch processing"},
    {"name": "Full UI", "module": "ui", "desc": "Complete interface with all features"},
    {"name": "Pro Mode", "module": "ui_pro", "desc": "Professional mode with advanced controls"},
    {"name": "Fast Mode", "module": "ui_fast", "desc": "Optimized for speed, CPU rendering"},
    {"name": "Simple Mode", "module": "ui_simple", "desc": "Simplified interface for beginners"},
    {"name": "Minimal", "module": "ui_minimal", "desc": "Minimal interface, basic features only"},
]


def launch_ui(module_name):
    """启动指定的 UI 模块"""
    dpg.destroy_context()

    if module_name == "ui_skybox":
        import ui_skybox
        ui_skybox.run()
    elif module_name == "ui":
        import ui
        ui.run()
    elif module_name == "ui_pro":
        import ui_pro
        ui_pro.run()
    elif module_name == "ui_fast":
        import ui_fast
        ui_fast.run()
    elif module_name == "ui_simple":
        import ui_simple
        ui_simple.run()
    elif module_name == "ui_minimal":
        import ui_minimal
        ui_minimal.run()


def on_select(sender, app_data, user_data):
    """选择 UI 版本回调"""
    module_name = user_data
    launch_ui(module_name)


def build():
    dpg.create_context()
    dpg.create_viewport(title=f"AutoToon Studio Launcher {VERSION}", width=500, height=400)

    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 35))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (50, 100, 180))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (70, 130, 210))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (220, 220, 220))
    dpg.bind_theme(t)

    with dpg.window(tag="main"):
        dpg.add_text(f"AutoToon Studio {VERSION}", color=(100, 180, 255))
        dpg.add_text("Select UI Version:", color=(180, 180, 180))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        for opt in UI_OPTIONS:
            with dpg.group():
                dpg.add_button(
                    label=opt["name"],
                    callback=on_select,
                    user_data=opt["module"],
                    width=300,
                    height=30
                )
                dpg.add_text(f"  {opt['desc']}", color=(120, 120, 120))
                dpg.add_spacer(height=5)

        dpg.add_separator()
        dpg.add_text("Press a button to launch the selected UI", color=(100, 100, 100))

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 50)
    print(f"AutoToon Studio Launcher {VERSION}")
    print("Select a UI version to start")
    print("=" * 50)

    build()

    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    run()
