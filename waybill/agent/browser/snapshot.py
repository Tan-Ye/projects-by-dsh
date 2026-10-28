"""把页面压成"模型能看懂的一段文本"。

整页 HTML 又长又吵，模型抓不住重点；只给可见元素的精简描述。

取舍：
    * 不取属性值里的长内容（style/class 截断到 40 字符）
    * 只取叶子节点的文本——父节点的 textContent 会把整棵子树糊在一起
    * 上限 300 条，超出就截断：花的是 token，不是硬盘
"""

from __future__ import annotations

from playwright.async_api import Page

_COLLECT = """
(limit) => {
  const skip = new Set(['script','style','svg','path','link','meta','noscript','br']);
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const el = walker.currentNode;
    const tag = el.tagName.toLowerCase();
    if (skip.has(tag)) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;

    const attrs = [];
    for (const name of ['id','name','type','class','href','title']) {
      const value = el.getAttribute(name);
      if (value) attrs.push(`${name}=${value.slice(0, 40)}`);
    }
    const text = el.childElementCount === 0 ? (el.textContent || '').trim().slice(0, 60) : '';
    out.push(`${tag} ${attrs.join(' ')} ${text}`.trim());
    if (out.length >= limit) break;
  }
  return out;
}
"""


async def snapshot_page(page: Page, *, limit: int = 300) -> str:
    """当前页面 → 元素清单。iframe 里的内容也收进来。

    明细表在 iframe 里，如果只取主文档，模型看不到它——自愈就会瞎猜。
    """
    lines: list[str] = [f"URL: {page.url}"]
    lines.extend(await page.evaluate(_COLLECT, limit))

    for frame in page.frames:
        if frame is page.main_frame:
            continue
        lines.append(f"--- frame: {frame.url} ---")
        lines.extend(await frame.evaluate(_COLLECT, limit))

    return "\n".join(lines)
