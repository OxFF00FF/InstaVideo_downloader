import glob
import os
import re
import sys
import time

import wget
import json
import requests
from urllib.parse import urlparse, urlunparse
from rich.console import Console
from rich.text import Text

console = Console()

call_count = 0
symbol_index = 0
symbols = ["-", "\\", "|", "/"]


def remove_query_params(url: str) -> str:
    parsed_url = urlparse(url)
    clean_url = parsed_url._replace(query='')
    return urlunparse(clean_url)


def bar_progress(current, total, width=80, f_name=None):
    global call_count, symbol_index

    current_mb = current / (1024 * 1024)
    total_mb = total / (1024 * 1024)
    percent_complete = current / total * 100

    call_count += 1
    if call_count % 100 == 0:
        symbol_index = (symbol_index + 1) % len(symbols)
    current_symbol = symbols[symbol_index]

    progress_message = f"*  Скачивается: {f_name}  {current_symbol}  [ {current_mb:.2f} / {total_mb:.1f} MB ] ({percent_complete:.0f}%)"

    sys.stdout.write("\r" + progress_message)
    sys.stdout.flush()


def download_video(post, output_dir):
    # from datetime import datetime
    # current_time = datetime.now().strftime("%Y-%m-%d_%H-%M")
    # url = post.get('url')
    # post_url = url.replace("instagram.com", "ddinstagram.com").replace("==", "%3D%3D")

    post_CODE = post.get('post_CODE')
    post_DESC = post.get('description')

    post_ID = f"/videos/{post_CODE}/1"
    download_url = f'https://ddinstagram.com{post_ID}'

    if post.get('video_url'):
        film_name = post_DESC.split('\n')[0]
        filename = re.sub(pattern=r'[\\/:*?"<>|]', repl='', string=f"{film_name[:150]} [{post_CODE}].mp4")

        output = os.path.join(output_dir, filename)
        wget.download(download_url, output, bar=lambda current, total, width: bar_progress(current, total, width, f_name=filename))
        console.print(f"\n+  Файл сохранен в `{output}`\n", style="green")
        time.sleep(1)
    else:
        console.print(f"#  Ошибка во время скачивания. Неверная ссылка либо пост не содержит видео\n", style="red")
        time.sleep(0.5)


def parse_page_info(response_json: dict) -> dict:
    top_level_key = "graphql" if "graphql" in response_json else "data"
    user_data = response_json[top_level_key].get("user", {})
    page_info = user_data.get("edge_owner_to_timeline_media", {}).get("page_info", {})
    return page_info


def parse_posts(response_json: dict) -> list:
    top_level_key = "graphql" if "graphql" in response_json else "data"
    user_data = response_json[top_level_key].get("user", {})
    post_edges = user_data.get("edge_owner_to_timeline_media", {}).get("edges", [])
    username = user_data.get("username")

    posts = []
    for node in post_edges:
        post_json = node.get("node", {})
        shortcode = post_json.get("shortcode")
        caption_edges = post_json.get("edge_media_to_caption", {}).get("edges", [])
        description = caption_edges[0].get("node", {}).get("text") if len(caption_edges) > 0 else ''
        video_url = post_json.get("video_url")

        frame_size = ''
        if post_json.get('__typename') == 'GraphVideo':
            dimensions = post_json.get('dimensions')
            H = dimensions.get('height')
            W = dimensions.get('width')
            frame_size = f"Разрешние видео: {H}x{W} пикселей"

        posts.append({
            "post_CODE": shortcode,
            "video_url": video_url,
            "description": description,
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "username": username,
            "frame_size": frame_size
        })
    return posts


def get_total_posts(response_json: dict) -> int:
    top_level_key = "graphql" if "graphql" in response_json else "data"
    user_data = response_json[top_level_key].get("user", {})
    posts_count = user_data.get("edge_owner_to_timeline_media", {}).get("count", [])
    return posts_count


def parse_ig_profile(username: str, n: int):
    if not os.path.exists('data'):
        os.makedirs('data')

    current_dir = os.path.dirname(os.path.realpath(__file__))
    data_dirs = glob.glob(os.path.join(current_dir, 'data'))
    if data_dirs:
        data_dir = data_dirs[0]
    else:
        data_dir = os.path.join(current_dir, 'data')
        os.makedirs(data_dir)

    headers = {'x-ig-app-id': '936619743392459'}
    r = requests.get(url=f'https://i.instagram.com/api/v1/users/web_profile_info/?username={username}', headers=headers)
    if not r:
        console.print(f"\nПользователь `{username}` не найден", style="red")
        sys.exit()

    response_json = r.json()
    user_id = response_json.get("data", {}).get("user", {}).get("id")
    posts = parse_posts(response_json=response_json)
    page_info = parse_page_info(response_json=response_json)
    total_post_count = get_total_posts(response_json=response_json)
    end_cursor = page_info.get("end_cursor")

    console.print(f"\n+------------------------------------------------------------+")
    console.print(f"`{username}` | `https://www.instagram.com/{username}`\n")
    console.print(f"Формируем список из {n * 12} постов для скачивания | Всего постов в профиле: {total_post_count}", style="yellow")

    i = 1
    console.print(f"Постов добавлено в очередь: {len(posts)}", style="yellow")
    while end_cursor and i < n:
        response_json = requests.get(f"https://instagram.com/graphql/query/?query_id=17888483320059182&id={user_id}&first=12&after={end_cursor}").json()
        posts.extend(parse_posts(response_json=response_json))
        page_info = parse_page_info(response_json=response_json)
        end_cursor = page_info.get("end_cursor")
        console.print(f"Постов добавлено в очередь: {len(posts)}", style="yellow")
        i += 1

    filename = f"posts ({username}).json"
    with open(os.path.join(data_dir, filename), "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=4)
        console.print(f"Файл со списком постов создан в `{os.path.join(data_dir, filename)}`", style="yellow")
    console.print(f'Готово\n', style="green")


def download_posts(username, n_posts):
    user_downloads_dir = os.path.join(os.environ['USERPROFILE'], 'Downloads')
    output_dir = os.path.join(user_downloads_dir, 'Instagram', username)

    if n_posts.isdigit():
        parse_ig_profile(username, int(n_posts))
    else:
        console.print(f'Количество должно быть числом', style="red")
        sys.exit()

    if not os.path.exists(os.path.join(user_downloads_dir, 'Instagram')):
        os.makedirs(os.path.join(user_downloads_dir, 'Instagram'))
        console.print(f'Папка `Instagram` создана в `{user_downloads_dir}`', style="yellow")
    else:
        console.print(f'Папка `Instagram` уже существует в `{user_downloads_dir}`', style="yellow")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        console.print(f'Папка `{username}` создана в `{output_dir}`', style="yellow")
        console.print(f'Готово\n', style="green")
    else:
        console.print(f'Папка `{username}` уже существует. Скачивание видео в папку `{output_dir}`\n', style="yellow")

    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data', f'posts ({username}).json')
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.loads(file.read())
        for e, post in enumerate(data):
            console.print(f"-  Обрабатывается [{e + 1} / {len(data)}] | {post['url']} | {post['frame_size']}", style='bright_cyan')
            download_video(post, output_dir)
    console.print(f"Готово. Все файлы успешно скачаны в папку `{os.path.join(user_downloads_dir, 'Instagram', username)}`", style="green")


if __name__ == '__main__':
    ig_profile = console.input(
        Text("Вставьте ссылку на профиль инстаграм или имя пользователя.\n"
             "Например: \n"
             " ·  https://www.instagram.com/lego/ \n"
             " ·  instagram.com/lego \n"
             " ·  lego\n", style='yellow')
        + Text("Сcылка или имя профиля инстаграм: ", style="cyan"))

    n_donwloads = console.input(
        Text(f"\nУкажите количество скачиваний. Одна единица равна 12 постам. (1 = 12 постов, 2 = 24 поста и тд.)\n", style='yellow')
        + Text(f"Количество постов: ", style="cyan"))

    download_posts(ig_profile, n_donwloads)
    console.print(f"+------------------------------------------------------------+")

    input('\nНажмите любую клавишу для выхода...')
