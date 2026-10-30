# -*- coding: utf-8 -*-
"""
把 build_web.py 產生的網頁版複製到 docs/，給 GitHub Pages 發布用。

用法：
    python build_web.py          # 先建置
    python deploy_pages.py       # 再複製到 docs/
    git add -A && git commit -m "更新網頁版" && git push

GitHub Pages 的設定（只要做一次）：
    repo 的 Settings -> Pages -> Build and deployment
    Source: Deploy from a branch
    Branch: main  /docs   -> Save

設定完的網址：https://jessechan27.github.io/aiproject/

為什麼用 docs/ 而不是 gh-pages 分支：docs/ 就在 main 上，不必維護第二個分支，
改完遊戲重新建置、複製、推送就更新了。
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "web_build", "build", "web")
DST = os.path.join(ROOT, "docs")


def main():
    if not os.path.isfile(os.path.join(SRC, "index.html")):
        print("找不到建置產物，請先執行：python build_web.py")
        return 1

    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)

    total = 0
    for name in sorted(os.listdir(SRC)):
        src = os.path.join(SRC, name)
        if not os.path.isfile(src):
            continue
        shutil.copy2(src, os.path.join(DST, name))
        size = os.path.getsize(src)
        total += size
        print("  %9.1f KB  %s" % (size / 1024, name))

    # 不加這個檔，GitHub Pages 會用 Jekyll 處理，底線開頭的檔案會被吃掉
    open(os.path.join(DST, ".nojekyll"), "w").close()
    print("  %9.1f KB  .nojekyll" % 0.0)

    print("\n已複製到 docs/，共 %.1f MB" % (total / 1048576))
    print("接著執行：git add -A && git commit -m \"更新網頁版\" && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
