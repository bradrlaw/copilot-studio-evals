#!/usr/bin/env python3
"""Render the synthetic banking-agent flow CSV as a high-resolution JPG."""

import argparse
import csv
import math
import textwrap
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BACKGROUND = "#F4F7FA"
PANEL = "#FFFFFF"
PANEL_BORDER = "#B8C4D1"
TITLE = "#172B4D"
TEXT = "#17242B"
MUTED = "#5E6C84"
EDGE = "#66788A"
USER_FILL = "#FFF3CD"
USER_BORDER = "#806000"
AGENT_FILL = "#DDEBFF"
AGENT_BORDER = "#174EA6"
SYSTEM_FILL = "#D9F2E6"
SYSTEM_BORDER = "#146C43"
DECISION_FILL = "#F3E5F5"
DECISION_BORDER = "#6A1B70"

CANVAS_WIDTH = 6000
MARGIN = 120
COLUMNS = 3
GAP = 70
PANEL_WIDTH = (CANVAS_WIDTH - 2 * MARGIN - (COLUMNS - 1) * GAP) // COLUMNS
PANEL_HEIGHT = 1520
HEADER_HEIGHT = 150
NODE_HEIGHT = 118
LAYER_GAP = 50


def load_font(name: str, size: int):
    candidates = [
        Path("C:/Windows/Fonts") / name,
        Path("/usr/share/fonts/truetype/dejavu") / name,
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONT_TITLE = load_font("segoeuib.ttf", 52)
FONT_SUBTITLE = load_font("segoeui.ttf", 28)
FONT_NODE = load_font("segoeui.ttf", 27)
FONT_NODE_BOLD = load_font("segoeuib.ttf", 25)
FONT_SMALL = load_font("segoeui.ttf", 21)
FONT_LEGEND = load_font("segoeui.ttf", 25)
FONT_POSTER = load_font("segoeuib.ttf", 70)


def read_flow(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    flow_order = []
    grouped = {}
    for row in rows:
        flow_id = row["flow_id"]
        if flow_id not in grouped:
            flow_order.append(flow_id)
            grouped[flow_id] = {"name": row["flow_name"], "nodes": [], "edges": []}
        grouped[flow_id]["nodes" if row["record_type"] == "node" else "edges"].append(row)
    return [(flow_id, grouped[flow_id]) for flow_id in flow_order]


def assign_layers(nodes, edges):
    node_ids = {node["id"] for node in nodes}
    outgoing = defaultdict(list)
    incoming = defaultdict(int)
    for edge in edges:
        if edge["from_id"] in node_ids and edge["to_id"] in node_ids:
            outgoing[edge["from_id"]].append(edge["to_id"])
            incoming[edge["to_id"]] += 1

    roots = [node["id"] for node in nodes if incoming[node["id"]] == 0]
    if not roots and nodes:
        roots = [nodes[0]["id"]]

    rank = {}
    queue = deque((root, 0) for root in roots)
    while queue:
        node_id, depth = queue.popleft()
        if node_id in rank and rank[node_id] <= depth:
            continue
        rank[node_id] = depth
        for child in outgoing[node_id]:
            queue.append((child, depth + 1))

    fallback = max(rank.values(), default=-1) + 1
    for node in nodes:
        if node["id"] not in rank:
            rank[node["id"]] = fallback
            fallback += 1

    layers = defaultdict(list)
    for node in nodes:
        layers[rank[node["id"]]].append(node)
    return [layers[index] for index in sorted(layers)]


def wrapped_lines(text, width):
    return textwrap.wrap(text, width=max(18, width), break_long_words=False)[:3]


def node_style(node):
    if node["shape"] == "decision":
        return DECISION_FILL, DECISION_BORDER
    if node["lane"] == "User":
        return USER_FILL, USER_BORDER
    if node["lane"] == "System":
        return SYSTEM_FILL, SYSTEM_BORDER
    return AGENT_FILL, AGENT_BORDER


def draw_centered_lines(draw, box, lines, font, fill, gap=3):
    x1, y1, x2, y2 = box
    heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    total = sum(heights) + gap * max(0, len(lines) - 1)
    y = y1 + (y2 - y1 - total) / 2
    for line, height in zip(lines, heights):
        bounds = draw.textbbox((0, 0), line, font=font)
        width = bounds[2] - bounds[0]
        draw.text(((x1 + x2 - width) / 2, y), line, font=font, fill=fill)
        y += height + gap


def draw_arrow(draw, points, color=EDGE, width=5):
    draw.line(points, fill=color, width=width, joint="curve")
    if len(points) < 2:
        return
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 18
    spread = math.pi / 7
    arrow = [
        (x2, y2),
        (x2 - length * math.cos(angle - spread), y2 - length * math.sin(angle - spread)),
        (x2 - length * math.cos(angle + spread), y2 - length * math.sin(angle + spread)),
    ]
    draw.polygon(arrow, fill=color)


def layout_panel(panel_box, nodes, edges):
    px1, py1, px2, py2 = panel_box
    layers = assign_layers(nodes, edges)
    content_top = py1 + HEADER_HEIGHT + 30
    content_bottom = py2 - 40
    available_height = content_bottom - content_top
    step = max(NODE_HEIGHT + 18, min(NODE_HEIGHT + LAYER_GAP, available_height // max(1, len(layers))))
    positions = {}

    for layer_index, layer in enumerate(layers):
        y = content_top + layer_index * step
        count = len(layer)
        inner_width = px2 - px1 - 100
        slot_width = inner_width / count
        node_width = min(720, slot_width - 28)
        for item_index, node in enumerate(layer):
            center = px1 + 50 + slot_width * (item_index + 0.5)
            positions[node["id"]] = (
                int(center - node_width / 2),
                int(y),
                int(center + node_width / 2),
                int(y + NODE_HEIGHT),
            )
    return positions


def render_panel(draw, panel_box, flow_id, flow):
    px1, py1, px2, py2 = panel_box
    draw.rounded_rectangle(panel_box, radius=28, fill=PANEL, outline=PANEL_BORDER, width=4)
    draw.text((px1 + 42, py1 + 30), flow["name"], font=FONT_TITLE, fill=TITLE)
    draw.text((px1 + 44, py1 + 94), flow_id, font=FONT_SUBTITLE, fill=MUTED)

    positions = layout_panel(panel_box, flow["nodes"], flow["edges"])
    node_ids = set(positions)

    for edge in flow["edges"]:
        if edge["from_id"] not in node_ids or edge["to_id"] not in node_ids:
            continue
        source = positions[edge["from_id"]]
        target = positions[edge["to_id"]]
        sx, sy = (source[0] + source[2]) // 2, source[3]
        tx, ty = (target[0] + target[2]) // 2, target[1]
        if ty >= sy:
            mid = (sy + ty) // 2
            points = [(sx, sy), (sx, mid), (tx, mid), (tx, ty)]
        else:
            detour_x = min(px2 - 28, max(source[2], target[2]) + 34)
            points = [(sx, sy), (detour_x, sy + 18), (detour_x, ty - 18), (tx, ty)]
        draw_arrow(draw, points)
        if edge["connector_label"]:
            label = edge["connector_label"]
            label_bounds = draw.textbbox((0, 0), label, font=FONT_SMALL)
            label_width = label_bounds[2] - label_bounds[0] + 16
            label_x = (sx + tx) // 2 - label_width // 2
            label_y = (sy + ty) // 2 - 14
            draw.rounded_rectangle(
                (label_x, label_y, label_x + label_width, label_y + 30),
                radius=8,
                fill=PANEL,
            )
            draw.text((label_x + 8, label_y + 2), label, font=FONT_SMALL, fill=MUTED)

    for node in flow["nodes"]:
        box = positions[node["id"]]
        fill, border = node_style(node)
        if node["shape"] == "decision":
            x1, y1, x2, y2 = box
            points = [
                ((x1 + x2) // 2, y1),
                (x2, (y1 + y2) // 2),
                ((x1 + x2) // 2, y2),
                (x1, (y1 + y2) // 2),
            ]
            draw.polygon(points, fill=fill, outline=border)
            draw.line(points + [points[0]], fill=border, width=4)
        else:
            draw.rounded_rectangle(box, radius=20, fill=fill, outline=border, width=4)

        width_chars = max(22, int((box[2] - box[0]) / 15))
        lines = wrapped_lines(node["text"], width_chars)
        draw_centered_lines(draw, box, lines, FONT_NODE, TEXT)

        meta = []
        if node["expected_tool"]:
            meta.append(node["expected_tool"])
        if node["acceptance_criteria_ids"]:
            meta.append(node["acceptance_criteria_ids"])
        if meta:
            meta_text = " | ".join(meta)
            meta_box = draw.textbbox((0, 0), meta_text, font=FONT_SMALL)
            meta_width = meta_box[2] - meta_box[0]
            draw.text(
                ((box[0] + box[2] - meta_width) / 2, box[3] + 5),
                meta_text,
                font=FONT_SMALL,
                fill=MUTED,
            )


def render(input_path: Path, output_path: Path):
    flows = read_flow(input_path)
    rows = math.ceil(len(flows) / COLUMNS)
    canvas_height = MARGIN + 210 + rows * PANEL_HEIGHT + (rows - 1) * GAP + MARGIN
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.text((MARGIN, 65), "Synthetic Banking Agent - Conversation Flows", font=FONT_POSTER, fill=TITLE)
    draw.text(
        (MARGIN, 150),
        "Fictional sample | Node colors identify responsibility | Tool names and acceptance criteria are illustrative",
        font=FONT_SUBTITLE,
        fill=MUTED,
    )

    legend_x = CANVAS_WIDTH - MARGIN - 1200
    for index, (label, fill, border) in enumerate(
        [
            ("User", USER_FILL, USER_BORDER),
            ("Agent", AGENT_FILL, AGENT_BORDER),
            ("System / tool", SYSTEM_FILL, SYSTEM_BORDER),
            ("Decision", DECISION_FILL, DECISION_BORDER),
        ]
    ):
        x = legend_x + (index % 2) * 580
        y = 55 + (index // 2) * 70
        draw.rounded_rectangle((x, y, x + 48, y + 38), radius=8, fill=fill, outline=border, width=3)
        draw.text((x + 62, y + 4), label, font=FONT_LEGEND, fill=TEXT)

    for index, (flow_id, flow) in enumerate(flows):
        row, column = divmod(index, COLUMNS)
        x1 = MARGIN + column * (PANEL_WIDTH + GAP)
        y1 = MARGIN + 210 + row * (PANEL_HEIGHT + GAP)
        render_panel(draw, (x1, y1, x1 + PANEL_WIDTH, y1 + PANEL_HEIGHT), flow_id, flow)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "JPEG", quality=94, optimize=True, progressive=True, dpi=(200, 200))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="data/source/banking-agent-miro-flow.csv",
        help="Source flow CSV",
    )
    parser.add_argument(
        "--output",
        default="data/source/banking-agent-flow.jpg",
        help="Output JPG",
    )
    args = parser.parse_args()
    render(Path(args.input), Path(args.output))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
