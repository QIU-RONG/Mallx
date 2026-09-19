package mbprobe;

import org.apache.ibatis.io.Resources;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;

import java.io.InputStream;

/**
 * Minimal validation of the one real unknown in Day 14 Step 4:
 * does an UPDATE ... RETURNING wrapped in a MyBatis <select> behave the way the
 * inventory_logs ledger design assumes?
 *
 * Assumptions under test:
 *   A1. <select resultType="java.lang.Integer"> around UPDATE..RETURNING executes at all.
 *   A2. It returns the AFTER value (post-update available_stock), not the before value.
 *   A3. When the WHERE guard matches 0 rows, it returns null (not 0, not an exception).
 *   A4. flushCache="true" is genuinely required: without it, a second identical call in the
 *       same SqlSession is served from the local cache and lies about the outcome.
 *
 * Everything runs inside ONE uncommitted transaction and is rolled back at the end,
 * so the database is left exactly as it was found.
 */
public class Probe {

    static int pass = 0;
    static int fail = 0;

    static void check(String name, Object expected, Object actual) {
        boolean ok = (expected == null) ? (actual == null) : expected.equals(actual);
        if (ok) {
            pass++;
            System.out.println("  [PASS] " + name + "  -> " + actual);
        } else {
            fail++;
            System.out.println("  [FAIL] " + name + "  expected=" + expected + " actual=" + actual);
        }
    }

    /** Returns [available, locked, sold] */
    static int[] snap(ProbeMapper m, long sku) {
        String s = m.readStock(sku);
        String[] p = s.split("/");
        return new int[]{Integer.parseInt(p[0]), Integer.parseInt(p[1]), Integer.parseInt(p[2])};
    }

    public static void main(String[] args) throws Exception {
        try (InputStream in = Resources.getResourceAsStream("mybatis-config.xml")) {
            SqlSessionFactory factory = new SqlSessionFactoryBuilder().build(in);
            SqlSession session = factory.openSession(false); // manual tx; never committed
            int a0, l0, s0;
            try {
                ProbeMapper m = session.getMapper(ProbeMapper.class);

                System.out.println("== T0: baseline ==");
                int[] base = snap(m, 4L);
                a0 = base[0]; l0 = base[1]; s0 = base[2];
                System.out.println("  sku 4 = available/locked/sold = " + a0 + "/" + l0 + "/" + s0);

                System.out.println("== T1 (A1,A2): deduct 1, guard passes ==");
                Integer r1 = m.probeDeduct(4L, 1);
                check("A1 returns a value at all", true, r1 != null);
                check("A2 returns AFTER value (before-1)", a0 - 1, r1);
                int[] t1 = snap(m, 4L);
                check("  available really decremented", a0 - 1, t1[0]);
                check("  locked really incremented", l0 + 1, t1[1]);
                check("  sold untouched", s0, t1[2]);

                System.out.println("== T2 (A3): deduct 999999, guard fails ==");
                Integer r2 = m.probeDeduct(4L, 999999);
                check("A3 returns NULL (not 0, not exception)", null, r2);
                int[] t2 = snap(m, 4L);
                check("  nothing changed", a0 - 1, t2[0]);

                System.out.println("== T3 (A2): release 1, back to baseline ==");
                Integer r3 = m.probeRelease(4L, 1);
                check("returns AFTER value == baseline", a0, r3);
                int[] t3 = snap(m, 4L);
                check("  available restored", a0, t3[0]);
                check("  locked restored", l0, t3[1]);

                System.out.println("== T4 (A4): identical params twice in SAME session, flushCache=true ==");
                m.probeDeduct(4L, 1);              // locked: l0 -> l0+1
                Integer c1 = m.probeRelease(4L, 1); // locked: l0+1 -> l0   (succeeds)
                Integer c2 = m.probeRelease(4L, 1); // locked: l0  -> fails guard
                check("1st release hits the DB", a0, c1);
                check("2nd release returns NULL (cache was flushed)", null, c2);
                check("  available not double-incremented", a0, snap(m, 4L)[0]);

                System.out.println("== T5 (A4 control): identical params twice, flushCache=FALSE ==");
                m.probeDeduct(4L, 1);                    // locked: l0 -> l0+1
                Integer n1 = m.probeReleaseNoFlush(4L, 1); // locked: l0+1 -> l0 (succeeds)
                Integer n2 = m.probeReleaseNoFlush(4L, 1); // guard fails, but cache may lie
                check("1st no-flush release hits the DB", a0, n1);
                System.out.println("  2nd no-flush release returned: " + n2
                        + (n2 == null
                           ? "   (null -> local cache not used here)"
                           : "   <<< STALE CACHE HIT (returned " + n2
                             + " without touching the DB) - this is exactly the trap"));
                int[] t5 = snap(m, 4L);
                System.out.println("  DB says available/locked = " + t5[0] + "/" + t5[1]);

                System.out.println("== T6: rollback ==");
                session.rollback();
            } catch (Exception e) {
                session.rollback();
                session.close();
                throw e;
            }
            session.close();

            SqlSession s2 = factory.openSession(false);
            int[] fin = snap(s2.getMapper(ProbeMapper.class), 4L);
            s2.close();
            System.out.println("  after rollback sku 4 = " + fin[0] + "/" + fin[1] + "/" + fin[2]);
            check("DB restored to baseline", a0, fin[0]);
            check("locked restored to baseline", l0, fin[1]);
            check("sold restored to baseline", s0, fin[2]);
        }

        System.out.println();
        System.out.println("RESULT: pass=" + pass + " fail=" + fail);
        if (fail > 0) {
            System.exit(1);
        }
    }
}
