import base64
import os

files = {
    'artifacts/zarvio/src/components/layout/Sidebar.tsx': r'D:\zarvio\frontend-main\frontend-main\artifacts\zarvio\src\components\layout\Sidebar.tsx',
    'artifacts/zarvio/src/App.tsx': r'D:\zarvio\frontend-main\frontend-main\artifacts\zarvio\src\App.tsx',
    'artifacts/zarvio/src/pages/dashboard/DealRoom.tsx': r'D:\zarvio\frontend-main\frontend-main\artifacts\zarvio\src\pages\dashboard\DealRoom.tsx',
    'artifacts/zarvio/src/pages/dashboard/Campaigns.tsx': r'D:\zarvio\frontend-main\frontend-main\artifacts\zarvio\src\pages\dashboard\Campaigns.tsx'
}

cmd = "python3 -c 'import base64, os\n"

for replit_path, local_path in files.items():
    with open(local_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    cmd += f"p = \"/home/runner/workspace/{replit_path}\"\nos.makedirs(os.path.dirname(p), exist_ok=True)\nwith open(p, \"wb\") as fil: fil.write(base64.b64decode(\"{data}\"))\n"

cmd += "print(\"UI Pages Synced!\")' && cd /home/runner/workspace && pnpm run build"

with open('sync_cmd.txt', 'w', encoding='utf-8') as f:
    f.write(cmd)

print("Generated sync command.")
