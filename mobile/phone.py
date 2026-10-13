"""ADB QA helper: derive every tap from a fresh accessibility tree."""
import argparse
import subprocess
import xml.etree.ElementTree as ET
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--serial', required=True)
parser.add_argument('action', choices=['dump', 'tap', 'text', 'back', 'screenshot'])
parser.add_argument('value', nargs='?')
parser.add_argument('--id', action='store_true')
parser.add_argument('--class-name', action='store_true')
args = parser.parse_args()
def adb(*command, capture=True):
    return subprocess.run(['adb', '-s', args.serial, *command], check=True, stdout=subprocess.PIPE if capture else None).stdout
def dump():
    raw = adb('exec-out', 'uiautomator', 'dump', '/dev/tty').decode()
    raw = raw[raw.index('<?xml'):raw.rindex('</hierarchy>') + len('</hierarchy>')]
    return ET.fromstring(raw)
if args.action in {'dump', 'tap'}:
    tree = dump()
    visible = []
    for node in tree.iter('node'):
        bounds = list(map(int, re.findall(r'\d+', node.attrib.get('bounds', ''))))
        if len(bounds) != 4 or bounds[0] == bounds[2] or bounds[1] == bounds[3]: continue
        if args.action == 'dump':
            label = node.attrib.get('text') or node.attrib.get('content-desc') or node.attrib.get('resource-id')
            if label or node.attrib.get('class') in {'android.widget.EditText', 'android.widget.CheckBox'}:
                print(node.attrib.get('class', '').rsplit('.',1)[-1], repr(label or ''), bounds)
        elif ((node.attrib.get('class') == args.value) if args.class_name else
              (node.attrib.get('resource-id', '').rsplit('/',1)[-1] == args.value) if args.id else
              (node.attrib.get('text') == args.value or node.attrib.get('content-desc') == args.value)):
            visible.append((node, bounds))
    if args.action == 'tap':
        # Android WebView can expose a link and its nested text as the same label.
        matches = {id(node) for node, _ in visible}
        visible = [(node, bounds) for node, bounds in visible
                   if not any(id(child) in matches for child in list(node.iter('node'))[1:])]
        if len(visible) != 1: raise SystemExit(f'Expected one visible match, found {len(visible)}')
        _, b = visible[0]
        adb('shell', 'input', 'tap', str((b[0]+b[2])//2), str((b[1]+b[3])//2))
        print('Tapped:', args.value)
elif args.action == 'text':
    adb('shell', 'input', 'text', args.value.replace(' ', '%s'))
elif args.action == 'back': adb('shell', 'input', 'keyevent', '4')
elif args.action == 'screenshot': Path(args.value).write_bytes(adb('exec-out', 'screencap', '-p'))
