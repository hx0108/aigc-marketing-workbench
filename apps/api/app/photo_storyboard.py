"""Frame-accurate photo storyboard used by the preview and the worker."""

def shot_plan(request, platform):
    photos = [entry["source_id"] for entry in request["photo_sources"]]
    worn_id = request.get("wear_source_id")
    main = worn_id or photos[0]
    alternates = [identifier for identifier in photos if identifier != main]
    seconds = request["duration_seconds"]
    # Leave sufficient screen time for each view. The remainder lands on the end frame.
    alternates = alternates[:min(4, max(1, seconds // 3 - 2))]
    views = ["scene", "packshot", *alternates, "end"]
    total_frames = seconds * 25
    weights = [4, 2, *([3] * len(alternates)), 3] if platform == "douyin" else [5, 3, *([3] * len(alternates)), 3]
    cuts = [0]
    for index in range(1, len(weights)):
        cuts.append(round(total_frames * sum(weights[:index]) / sum(weights)))
    cuts.append(total_frames)
    return [(view, (end-start)/25) for view, start, end in zip(views, cuts, cuts[1:])]
