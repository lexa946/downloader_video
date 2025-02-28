from app.schemas.main import SVideo

def get_formats(video_info):
    formats_all = video_info.get('formats', [])
    video_formats = {}
    audio_format_id = ""
    min_height = 144


    for format in formats_all:
        if format['resolution'] == 'audio only':
            audio_format_id = format['format_id']
            continue
        if "height" not in format or not format['height'] or format['height'] < min_height:
            continue
        video_formats[f"{format["height"]}p"] = format

    available_formats = [
        SVideo(
            **{
                "quality": key,
                "video_format_id": format['format_id'],
                "audio_format_id": audio_format_id,
            }
        ) for key, format in video_formats.items()
    ]
    return available_formats
