\pset border 2

\echo '===== ① 正确：列表带归属条件 · demo(user_id=1) → 期望 2 行 ====='
SELECT p.id, p.payment_no, p.order_id, o.order_no, p.amount, p.method, p.status
FROM payments p
         INNER JOIN orders o ON o.id = p.order_id
WHERE o.user_id = 1
ORDER BY p.id DESC;

\echo '===== ② 正确：列表带归属条件 · intruder(user_id=2) → 期望 0 行 ====='
SELECT p.id, p.payment_no, p.order_id, o.order_no, p.amount, p.method, p.status
FROM payments p
         INNER JOIN orders o ON o.id = p.order_id
WHERE o.user_id = 2
ORDER BY p.id DESC;

\echo '===== ③ 错误：列表【漏掉】归属条件 · 任何人看到的都是全量 → 2 行全泄漏 ====='
SELECT p.id, p.payment_no, p.order_id, o.order_no, p.amount, p.method, p.status
FROM payments p
         INNER JOIN orders o ON o.id = p.order_id
ORDER BY p.id DESC;

\echo '===== ④ 错误：详情【只按 p.id 查】· intruder 查 id=44 → 1 行泄漏 ====='
SELECT p.id, p.payment_no, p.order_id, o.order_no, p.amount, p.method, p.status
FROM payments p
         INNER JOIN orders o ON o.id = p.order_id
WHERE p.id = 44;

\echo '===== ⑤ 正确：详情带归属 · intruder 查 id=44 → 期望 0 行 ====='
SELECT p.id, p.payment_no, p.order_id, o.order_no, p.amount, p.method, p.status
FROM payments p
         INNER JOIN orders o ON o.id = p.order_id
WHERE p.id = 44
  AND o.user_id = 2;

\echo '===== ⑥ 正确：详情带归属 · demo 查 id=44 → 期望 1 行（同一条记录，两种结果）====='
SELECT p.id, p.payment_no, p.order_id, o.order_no, p.amount, p.method, p.status
FROM payments p
         INNER JOIN orders o ON o.id = p.order_id
WHERE p.id = 44
  AND o.user_id = 1;

\echo '===== ⑦ 反证 LEFT JOIN：payments.order_id 是 NOT NULL + 外键 → 它是 INNER 的子集 ====='
SELECT count(*) AS inner_rows
FROM payments p INNER JOIN orders o ON o.id = p.order_id;
SELECT count(*) AS left_rows
FROM payments p LEFT JOIN orders o ON o.id = p.order_id;
