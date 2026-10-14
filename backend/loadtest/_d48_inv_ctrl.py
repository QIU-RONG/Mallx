# -*- coding: utf-8 -*-
"""Day 48 · 库存单测的控制组（证明 InventoryServiceImplTest 有牙）。

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，
  脚本必须失败；失败数 = 0 就说明什么都没守住。

本脚本对 InventoryServiceImpl 做 6 处针对性变异，每处对应一条"如果这条断言没写，
这个 bug 就会溜过去"的设计意图：

  ① PAY_SOLD 的 change 改成 -quantity   → 应红 A2 + C2（Day 13 事故的原形）
  ② deductForOrder 的 400 改成 500      → 应红 B1（400/500 分野）
  ③ releaseLocked 把 writeLog 提到判 null 之前 → 应红 C1（孤儿流水）
  ④ listSkus 去掉夹紧                   → 应红 E1/E2/E3/E4
  ⑤ 去掉空串归一化                      → ★ 期望【0 条红】（证明测试文件里那句
                                          "单测覆盖不到、由 day17-f 覆盖"是诚实的，
                                          而不是一条恒真的假绿）
  ⑥ 删掉 adjust 的 delta == 0 守卫      → 应红 D1

⚠️ 两条本轮重踩的坑（照旧处理）：
  · 变异必须【先内存备份再写】，写完【立刻读回校验】，跑完【还原 + 读回校验】；
    否则一处没还原，后面几组的失败数会累积，看起来像"护栏在某些变异下不灵敏"。
  · 只看 mvn 退出码不够，要解析失败的【测试方法名】—— 那才是"哪条守住了"的证据。
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
IMPL = "mall-inventory/src/main/java/com/mallx/inventory/service/impl/InventoryServiceImpl.java"

_backup = {}
results = []


def _path(rel):
    return os.path.join(MODULE_DIR, rel.replace("/", os.sep))


def _nl(rel):
    """★ 源文件是 CRLF（实测 327 处）。读写必须保留原换行风格，
       否则一次「改两行 + 还原」会把整文件的换行符换掉 ⇒ git diff 全红，
       而控制组的「还原检查」也会误判成「没还原」。"""
    with open(_path(rel), "rb") as f:
        return "\r\n" if b"\r\n" in f.read() else "\n"


def read(rel):
    # newline 默认（universal）⇒ 读到的是 \n 归一化文本，pattern 才好写
    return io.open(_path(rel), encoding="utf-8").read()


def write(rel, text):
    io.open(_path(rel), "w", encoding="utf-8", newline=_nl(rel)).write(text)
    # ★ 写完立刻读回校验（本轮第 2 次栽在"写成功但内容没变"上）
    return io.open(_path(rel), encoding="utf-8").read() == text


def mutate(rel, old, new):
    if rel not in _backup:
        _backup[rel] = read(rel)
    s = _backup[rel]
    assert old in s, "pattern not found:\n%s" % old[:120]
    ok = write(rel, s.replace(old, new, 1))
    assert ok, "WRITE DID NOT LAND: %s" % rel
    return True


def restore(rel):
    ok = write(rel, _backup[rel])
    assert ok, "RESTORE DID NOT LAND: %s" % rel
    return ok


def run_tests():
    env = dict(os.environ, MAVEN_OPTS="-Xmx1024m")
    p = subprocess.run([MAVEN, "-o", "test", "-pl", "mall-inventory"],
                       cwd=MODULE_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", out)
    total, fails, errs = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (-1, -1, -1)
    # ★ 排除 `InventoryServiceImplTest.java:226` 这类【编译告警行】——
    #   第一版正则会把 "java" 当成一个测试方法名收进来。
    names = re.findall(r"InventoryServiceImplTest\.(?!java:)([A-Za-z0-9_]+):\d+", out)
    return p.returncode, total, fails + errs, sorted(set(names)), out


def case(title, rel, old, new, expect):
    mutate(rel, old, new)
    rc, total, bad, names, out = run_tests()
    restore(rel)
    ok = (bad == len(expect)) and all(n in names for n in expect)
    results.append((ok, title, bad, names, expect))
    print("\n%s  %s" % ("[OK]  " if ok else "[BAD] ", title))
    print("      rc=%s  tests=%s  failed=%d  %s" % (rc, total, bad, names or "-"))
    print("      expected=%s" % (expect or "0 条（本变异应当无人拦住）"))
    if not ok:
        print("      ★ 期望与实际不符 —— 这条断言要么缺牙、要么多抓了")


def main():
    print("=" * 74)
    print("Day 48 · InventoryServiceImplTest 控制组")
    print("=" * 74)

    # 基线：未变异时必须 0 红
    rc, total, bad, names, _ = run_tests()
    print("\n[基线] tests=%s failed=%d rc=%s %s" % (total, bad, rc, names or ""))
    if bad != 0:
        print("★ 基线就不是 0 红 ⇒ 先修测试，再谈控制组")
        return 1
    if total != 21:
        print("★ 基线条数 %s != 21 ⇒ 有测试没被创建（假绿的经典形态）" % total)
        return 1

    # ★ ① 的期望【只有 1 条】：C2 那条恒等式对「change 传错」无感 ——
    #   writeLog 内部是 before = after - change，所以不管调用方传什么 change，
    #   恒等式都成立。⇒ C2 守的是「writeLog 的构造不被改歪」（见 ①b），
    #   它【守不住】「某个写点传错了 change」（那是 A2 的职责）。
    #   ★ 这是本轮最值钱的一条教训：断言能拦什么必须说清，
    #     说不清就会把「构造保证的恒真」误当成「覆盖了业务取值」。
    case("① PAY_SOLD 的 change 改成 -quantity（同一件货被扣两遍）",
         IMPL,
         'writeLog(skuId, InventoryLogType.PAY_SOLD, 0, after, orderId);',
         'writeLog(skuId, InventoryLogType.PAY_SOLD, -quantity, after, orderId);',
         ["moveLockedToSold_changeIsAlwaysZero"])

    # ★ 期望 5 条而不是 1 条：before 被改歪后，A1/A3/A4/D4 里那些「before 的具体值」
    #   断言也会一起红（A2 不红，因为它 change == 0，加和减结果相同）。
    #   ⇒ 顺带证明：C2 不是唯一守着恒等式的，每条写点测试也在守。
    case("①b 把 writeLog 的 before 改成 after + change（破坏构造保证的恒等式）",
         IMPL,
         'log.setBeforeStock(after - change);',
         'log.setBeforeStock(after + change);',
         ["ledgerIdentityHoldsForEveryWritePath", "deductForOrder_writesLockLog",
          "releaseLocked_writesReleaseLog", "returnToStock_writesReturnLog",
          "adjust_negativeDelta_stillWritesLog"])

    case("② deductForOrder 的 0 行从 400 改成 500",
         IMPL,
         'throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "库存不足");',
         'throw new BusinessException(ResultCode.FAIL.getCode(), "库存不足");',
         ["deductForOrder_zeroRows_isBadRequest"])

    case("③ releaseLocked 先写流水再判 null（制造孤儿流水）",
         IMPL,
         """        Integer after = inventoryMapper.releaseLocked(skuId, quantity);
        if (after == null) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，取消已回滚");
        }
        // available 增加了 quantity，所以 change = +quantity
        writeLog(skuId, InventoryLogType.CANCEL_RELEASE, quantity, after, orderId);""",
         """        Integer after = inventoryMapper.releaseLocked(skuId, quantity);
        writeLog(skuId, InventoryLogType.CANCEL_RELEASE, quantity, after == null ? 0 : after, orderId);
        if (after == null) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，取消已回滚");
        }""",
         ["noOrphanLogWhenUpdateAffectsZeroRows"])

    case("④ listSkus 去掉分页夹紧",
         IMPL,
         """    public PageResult<InventoryVO> listSkus(long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);""",
         """    public PageResult<InventoryVO> listSkus(long page, long size) {
        long safePage = page;
        long safeSize = size;""",
         # ★ 期望【只有 3 条】：E4（page 方向）不会红 ——
         #   MyBatis-Plus 的 new Page<>(current, size) 对 current <= 0 自带兜底（保持 1），
         #   所以就算把 Math.max(page, 1) 删掉，E4 依然通过 ⇒ E4 是弱断言（已在测试里写明）。
         #   ★ 真正的洞在 size 方向（MP 不兜，size<=0 = 查全表），那才是 L1 要堵的。
         ["listSkus_negativeSize_clampedToLowerBound", "listSkus_zeroSize_clampedToOne",
          "listSkus_hugeSize_clampedToUpperBound"])

    case("⑤ 去掉空串归一化 —— ★ 期望【无人拦住】（证明注释里那句「单测覆盖不到」是真的）",
         IMPL,
         'String safeType = (type == null || type.isBlank()) ? null : type;',
         'String safeType = type;',
         [])

    case("⑥ 删掉 adjust 的 delta == 0 守卫",
         IMPL,
         """        if (delta == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "调整量不能为 0");
        }
""",
         "",
         ["adjust_zeroDelta_rejectedBeforeTouchingDb"])

    # 收尾：确认工作区干净（变异全部还原）
    p = subprocess.run(["git", "status", "--short", "--", IMPL],
                       cwd=os.path.dirname(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    dirty = [l for l in (p.stdout or "").splitlines() if l.strip()]
    print("\n" + "=" * 74)
    print("还原检查：%s" % ("干净 ✅" if not dirty else "★ 仍有改动 → %s" % dirty))

    bad_cases = [r for r in results if not r[0]]
    print("控制组：%d 组，符合预期 %d 组" % (len(results), len(results) - len(bad_cases)))
    for ok, title, bad, names, expect in results:
        print("  %s 失败 %d 条  %s" % ("[OK] " if ok else "[BAD]", bad, title[:44]))
    print("VERDICT: %s" % ("OK —— 每一组都按预期响" if not bad_cases and not dirty
                           else "FAIL —— 有组没按预期响，或变异没还原"))
    return 0 if (not bad_cases and not dirty) else 1


if __name__ == "__main__":
    sys.exit(main())
