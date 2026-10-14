# -*- coding: utf-8 -*-
"""Day 48 · 购物车单测的控制组（证明 CartServiceImplTest 有牙）。

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，脚本必须失败；
  失败数 = 0 就说明什么都没守住。

本脚本对 CartServiceImpl 做 6 处针对性变异：

  ① 库存守卫比【本次数量】而不是【合并后】  → 应红 B2（并发合并的真陷阱）
  ② 新加入的项默认【不勾选】               → 应红 B3
  ③ requireOwn 的 404 改成 400              → 应红 H1（IDOR 伪装）
  ④ 失效项也计入勾选金额                    → 应红 G2 + G6（会收错钱）
  ⑤ 失效理由优先级反过来（先判下架再判删除）→ 应红 G3
  ⑥ removeItem 去掉归属校验                 → ★ 期望【0 条红】
      （这一组是故意用来【暴露覆盖缺口】的：如果它真的 0 红，
        说明 removeItem 的越权根本没有测试守着 —— 那就补一条，而不是改期望。）

⚠️ 复用手账：源文件是 CRLF ⇒ 读写必须保留换行风格，否则还原会把整文件换行符换掉。
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # backend
MAVEN = r"D:\Maven\apache-maven-3.9.15\bin\mvn.cmd"
MODULE_DIR = os.path.join(REPO, "mallx")
IMPL = "mall-cart/src/main/java/com/mallx/cart/service/impl/CartServiceImpl.java"

_backup = {}
results = []


def _path(rel):
    return os.path.join(MODULE_DIR, rel.replace("/", os.sep))


def _nl(rel):
    with open(_path(rel), "rb") as f:
        return "\r\n" if b"\r\n" in f.read() else "\n"


def read(rel):
    return io.open(_path(rel), encoding="utf-8").read()


def write(rel, text):
    io.open(_path(rel), "w", encoding="utf-8", newline=_nl(rel)).write(text)
    return io.open(_path(rel), encoding="utf-8").read() == text


def mutate(rel, old, new):
    if rel not in _backup:
        _backup[rel] = read(rel)
    s = _backup[rel]
    assert old in s, "pattern not found:\n%s" % old[:150]
    assert write(rel, s.replace(old, new, 1)), "WRITE DID NOT LAND: %s" % rel


def restore(rel):
    assert write(rel, _backup[rel]), "RESTORE DID NOT LAND: %s" % rel


def run_tests():
    env = dict(os.environ, MAVEN_OPTS="-Xmx1024m")
    p = subprocess.run([MAVEN, "-o", "test", "-pl", "mall-cart"],
                       cwd=MODULE_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", out)
    total, bad = (int(m.group(1)), int(m.group(2)) + int(m.group(3))) if m else (-1, -1)
    names = re.findall(r"CartServiceImplTest\.(?!java:)([A-Za-z0-9_]+):\d+", out)
    return p.returncode, total, bad, sorted(set(names)), out


def case(title, rel, old, new, expect):
    mutate(rel, old, new)
    rc, total, bad, names, out = run_tests()
    restore(rel)
    ok = (bad == len(expect)) and all(n in names for n in expect)
    results.append((ok, title, bad, names, expect))
    print("\n%s  %s" % ("[OK]  " if ok else "[BAD] ", title))
    print("      rc=%s tests=%s failed=%d  %s" % (rc, total, bad, names or "-"))
    print("      expected=%s" % (expect or "0 条（本变异应当无人拦住）"))


def main():
    print("=" * 74)
    print("Day 48 · CartServiceImplTest 控制组")
    print("=" * 74)

    rc, total, bad, names, _ = run_tests()
    print("\n[基线] tests=%s failed=%d rc=%s %s" % (total, bad, rc, names or ""))
    if bad != 0:
        print("★ 基线就不是 0 红 ⇒ 先修测试，再谈控制组")
        return 1
    if total != 16:
        print("★ 基线条数 %s != 16 ⇒ 有测试没被创建（假绿的经典形态）" % total)
        return 1

    case("① 库存守卫比【本次数量】而不是【合并后】",
         IMPL,
         "if (merged > sku.getAvailableStock())",
         "if (dto.getQuantity() > sku.getAvailableStock())",
         ["addToCart_mergedExceedsStock_rejected"])

    case("② 新加入的项默认【不勾选】",
         IMPL,
         "item.setSelected(true);",
         "item.setSelected(false);",
         ["addToCart_newItemDefaultsSelected"])

    # ★ 期望 2 条而不是 1 条：requireOwn 被 C2（重复删）和 H1（改别人的）共用，
    #   所以它的错误码一改，两条都红 —— 这是「共用判定被改」的正常形态。
    case("③ requireOwn 的 404 改成 400（丢掉 IDOR 伪装）",
         IMPL,
         '''        if (item == null || !item.getUserId().equals(userId)) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "购物车项不存在");
        }''',
         '''        if (item == null || !item.getUserId().equals(userId)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "购物车项不存在");
        }''',
         ["updateQuantity_otherUsersItem_is404Not403", "removeItem_twice_secondIs404",
          "removeItem_otherUsersItem_is404AndNotDeleted"])

    # ★ 期望只有 G2 一条：G6 那条测的是「未勾选」—— selected=false 时
    #   不管有没有失效项过滤，勾选统计都是 0 ⇒ 它对这处改动天然无感。
    #   （第一版把 G6 也写进期望，是又一处「高估了断言的分辨力」。）
    case("④ 失效项也计入勾选金额（用户会为买不到的东西付钱）",
         IMPL,
         "if (!it.isInvalid() && Boolean.TRUE.equals(it.getSelected())) {",
         "if (Boolean.TRUE.equals(it.getSelected())) {",
         ["getCart_invalidItem_excludedFromSelectedTotals"])

    case("⑤ 失效理由优先级反过来（先判下架、再判删除）",
         IMPL,
         '''            } else if (Integer.valueOf(1).equals(it.getProductDeleted())) {
                it.setInvalid(true);
                it.setInvalidReason("商品已删除");
            } else if (!Integer.valueOf(1).equals(it.getProductStatus())) {
                it.setInvalid(true);
                it.setInvalidReason("商品已下架");''',
         '''            } else if (!Integer.valueOf(1).equals(it.getProductStatus())) {
                it.setInvalid(true);
                it.setInvalidReason("商品已下架");
            } else if (Integer.valueOf(1).equals(it.getProductDeleted())) {
                it.setInvalid(true);
                it.setInvalidReason("商品已删除");''',
         ["getCart_invalidReasonPicksMostFundamental"])

    # ★ 这一组第一跑时「期望 0 条红」，结果红的是 removeItem_twice_secondIs404 ——
    #   但它红的原因是【stub 了 selectById 却没被调用】触发 Mockito strict stubbing，
    #   不是安全断言生效。⇒ 删别人购物车项的越权当时真的没有测试守着。
    #   ★ 教训：变异后有测试红 ≠ 守住了。必须看【是哪条红、为什么红】——
    #     strict stubbing 的「未使用 stub」会制造一条与安全无关的红。
    #   已补 H2（removeItem 别人的项 → 404 且 never deleteById），本组现在应红 H2。
    # ★★ 本组期望 2 条，而且两条的「含金量」完全不同 —— 这是本轮最值得记的一条：
    #   · removeItem_otherUsersItem_is404AndNotDeleted = 【真证据】：H2 断言了 never deleteById
    #   · removeItem_twice_secondIs404               = 【假信号】：变异后 removeItem 不再调
    #     selectById ⇒ C2 stub 的 selectById 没人用 ⇒ Mockito strict stubbing 报
    #     UnnecessaryStubbingException。它与「越权守没守住」无关，只说明调用路径变了。
    #   ⇒ 教训：变异后【必须逐条看是哪条红、为什么红】。只数失败数会以为「守得很好」，
    #     其中一条其实跟安全无关；反过来也可能把假信号当成覆盖度的证据。
    case("⑥ removeItem 去掉归属校验（★ H2 是真证据；C2 是 strict stubbing 的假信号）",
         IMPL,
         '''    public void removeItem(Long userId, Long itemId) {
        CartItem item = requireOwn(userId, itemId);
        // cart_items 没有 is_deleted 列 → 真 DELETE；重复删第二次 selectById 返回 null → 404
        cartItemMapper.deleteById(item.getId());
    }''',
         '''    public void removeItem(Long userId, Long itemId) {
        cartItemMapper.deleteById(itemId);
    }''',
         ["removeItem_otherUsersItem_is404AndNotDeleted", "removeItem_twice_secondIs404"])

    p = subprocess.run(["git", "status", "--short", "--", IMPL],
                       cwd=os.path.dirname(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    dirty = [l for l in (p.stdout or "").splitlines() if l.strip()]
    print("\n" + "=" * 74)
    print("还原检查：%s" % ("干净 ✅" if not dirty else "★ 仍有改动 → %s" % dirty))
    bad_cases = [r for r in results if not r[0]]
    print("控制组：%d 组，符合预期 %d 组" % (len(results), len(results) - len(bad_cases)))
    for ok, title, bad, names, expect in results:
        print("  %s 失败 %d 条  %s" % ("[OK] " if ok else "[BAD]", bad, title[:46]))
    print("VERDICT: %s" % ("OK —— 每一组都按预期响" if not bad_cases and not dirty
                           else "FAIL —— 有组没按预期响，或变异没还原"))
    return 0 if (not bad_cases and not dirty) else 1


if __name__ == "__main__":
    sys.exit(main())
