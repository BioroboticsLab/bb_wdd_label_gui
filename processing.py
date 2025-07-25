import argparse
import csv
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from ffmpeg import FFmpeg
from tqdm import tqdm

from main import DATA_FILE, TAGGED_DANCE_DIR, UNTAGGED_DANCE_DIR, TagStatus


def main() -> None:
    """Processes WDD data into the expected format for the interface."""
    parser = init_argparse()
    args = parser.parse_args()
    if not args.input_dir.exists():
        print(f"Error: {args.input_dir} does not exist.")
        return
    if not args.input_dir.is_dir():
        print(f"Error: {args.input_dir} is not a valid directory.")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for zip_path in tqdm(list(args.input_dir.rglob("*.zip"))):
        daily_target = args.output_dir / zip_path.stem
        # Ignore days that were already processed.
        if daily_target.exists():
            print(f"{daily_target} already exists.")
            continue
        with ZipFile(zip_path) as zip_file:
            day_dance_ids = []
            waggle_ids = []
            dance_types = []

            tagged_target_dir = daily_target / TAGGED_DANCE_DIR
            untagged_target_dir = daily_target / UNTAGGED_DANCE_DIR
            tagged_target_dir.mkdir(parents=True, exist_ok=True)
            untagged_target_dir.mkdir(parents=True, exist_ok=True)

            video_filenames = list(
                filter(lambda filename: filename.endswith(".apng"), zip_file.namelist())
            )
            count = 1
            for video_filename in tqdm(video_filenames):
                # Find matching metadata file
                metadata_filename = video_filename.replace("frames.apng", "waggle.json")
                with zip_file.open(metadata_filename) as metadata_file:
                    json_data = json.load(metadata_file)
                # We only care about waggles, so filter the rest out.
                if json_data["predicted_class_label"] != "waggle":
                    continue
                day_dance_id = f"{count:04d}"
                day_dance_ids.append(day_dance_id)
                waggle_ids.append(json_data["waggle_id"])
                dance_types.append(json_data["predicted_class_label"])
                with tempfile.TemporaryDirectory() as tmp_dir:
                    # Files within the zip file are named like this:
                    # "12/44/8/frames.apng". This gives us a nested directory
                    # structure. We want a flat structure instead. Therefore,
                    # we assign a new name to the filename attribute of the
                    # video file which doesn't contain slashes and uniquely
                    # identifies the file.
                    # For example, "12/44/8/frames.apng" is renamed to "0001.apng".
                    zip_file.getinfo(video_filename).filename = day_dance_id + ".apng"
                    zip_file.extract(video_filename, tmp_dir)
                    input = Path(tmp_dir) / (day_dance_id + ".apng")
                    output = untagged_target_dir / (day_dance_id + ".mp4")
                    encode_video(input, output)
                count += 1

            data = {
                "day_dance_id": day_dance_ids,
                "waggle_id": waggle_ids,
                "category": len(day_dance_ids) * [TagStatus.untagged.value],
                "category_label": len(day_dance_ids) * [TagStatus.untagged.name],
                "confidence": len(day_dance_ids) * [""],
                "corrected_category": len(day_dance_ids) * [""],
                "corrected_category_label": len(day_dance_ids) * [""],
                "dance_type": dance_types,
                "corrected_dance_type": len(day_dance_ids) * [""],
            }
            with open(daily_target / DATA_FILE, "w") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(data.keys())
                writer.writerows(zip(*data.values()))


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s <input_dir> <output_dir>",
        description=(
            "Processes zipped WDD data from <input_dir> into the expected format "
            "for the Bee Tag Corrector Interface, and saves it in <output_dir>."
        ),
    )
    parser.add_argument(
        "input_dir", type=Path, help="Path to the directory containing zipped WDD data"
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Path to the directory where processed output will be stored",
    )
    return parser


def encode_video(input: Path, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = (
        FFmpeg()
        .option("y")
        .input(str(input))
        .output(str(output), {"codec:v": "libx264"}, crf=18, pix_fmt="yuv420p")
    )
    ffmpeg.execute()


if __name__ == "__main__":
    main()
