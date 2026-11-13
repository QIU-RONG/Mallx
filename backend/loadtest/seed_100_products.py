# -*- coding: utf-8 -*-
"""Day 126：为 MallX 生成 100 件演示商品（25 个型号 × 4 个规格变体）。

可重复执行：按 sku_code 前缀判断是否已灌过，避免重复。
"""
import json
import os
import random
import sys

import psycopg2

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "5433")),
          dbname=os.getenv("DB_NAME", "mallx"), user=os.getenv("DB_USERNAME", "mallx"),
          password=os.getenv("DB_PASSWORD", "mallx123"))

MODELS = [
    # 手机（品类 11）
    ("iPhone 16", 1, 11, 6999, 1), ("iPhone 16 Pro", 1, 11, 8999, 1),
    ("Huawei Mate 70", 2, 11, 5499, 1), ("Huawei P80", 2, 11, 4499, 1),
    ("Xiaomi 15", 3, 11, 3999, 2), ("Xiaomi 15 Ultra", 3, 11, 6499, 2),
    ("Samsung Galaxy S25", 4, 11, 5999, 1), ("Samsung Galaxy S25 Ultra", 4, 11, 9699, 1),
    ("Redmi K80", 3, 11, 2499, 2), ("OnePlus 13", 7, 11, 4299, 1),
    # 笔记本（21）
    ("Lenovo ThinkPad X1 Carbon", 5, 21, 12999, 1), ("Lenovo Yoga Pro 14", 5, 21, 7999, 1),
    ("Apple MacBook Air M4", 1, 21, 8999, 3), ("Apple MacBook Pro 14", 1, 21, 14999, 3),
    ("Huawei MateBook X Pro", 2, 21, 11999, 1), ("RedmiBook Pro 16", 3, 21, 5999, 2),
    # 电视（31）
    ("Xiaomi TV S Pro 65", 3, 31, 3999, 2), ("Xiaomi TV S Pro 75", 3, 31, 5999, 2),
    ("Samsung Neo QLED 65", 4, 31, 9999, 1), ("Samsung OLED 55", 4, 31, 7999, 1),
    ("Huawei Vision 75", 2, 31, 6499, 1),
    # 耳机（12）
    ("AirPods Pro 3", 1, 12, 1899, 3), ("Xiaomi Buds 5", 3, 12, 499, 2),
    ("Huawei FreeBuds Pro 4", 2, 12, 1499, 1), ("Samsung Galaxy Buds3", 4, 12, 999, 1),
]

VARIANTS = [("128GB", "黑色", 0), ("256GB", "白色", 400), ("512GB", "蓝色", 1000), ("1TB", "钛金属", 2000)]
ACCESSORY_VARIANTS = [("标准版", "黑色", 0), ("标准版", "白色", 0), ("降噪版", "黑色", 200), ("降噪版", "白色", 200)]
TV_VARIANTS = [("55 英寸", "黑色", 0), ("65 英寸", "黑色", 1500), ("75 英寸", "黑色", 3000), ("85 英寸", "黑色", 6000)]

DESC = {
    11: "全新一代旗舰手机，影像与性能全面升级。",
    21: "轻薄高性能笔记本，适合办公与创作。",
    31: "高色域 4K 智能电视，支持远场语音。",
    12: "主动降噪，低延迟连接，长续航。",
}


def main() -> int:
    random.seed(42)
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM product_skus WHERE sku_code LIKE 'DEMO-%'")
    if cur.fetchone()[0] > 0:
        print("已存在演示商品，跳过")
        return 0

    created = 0
    for model, brand_id, cat_id, base_price, shop_id in MODELS:
        variants = ACCESSORY_VARIANTS if cat_id == 12 else TV_VARIANTS if cat_id == 31 else VARIANTS
        for spec, color, extra in variants:
            name = f"{model} {spec} {color}"
            price = base_price + extra
            img = f"https://picsum.photos/seed/mallx{created + 1}/600/600"
            cur.execute(
                "INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image,"
                " status, is_deleted, shop_id) VALUES (%s, %s, %s, %s, %s, %s, 1, 0, %s) RETURNING id",
                (cat_id, brand_id, name, f"{model} · {spec} · {color}", DESC[cat_id], img, shop_id),
            )
            pid = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO product_images (product_id, image_url, sort_order) VALUES (%s, %s, 0)", (pid, img))
            first_sku = None
            for si in range(2):
                sku_color = color if si == 0 else "银色"
                sku_code = f"DEMO-{pid}-{si + 1}"
                cur.execute(
                    "INSERT INTO product_skus (product_id, sku_code, name, price, original_price,"
                    " attributes, image, status, is_deleted) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 1, 0) RETURNING id",
                    (pid, sku_code, f"{spec} {sku_color}", price, round(price * 1.15, 2),
                     json.dumps({"颜色": sku_color, "规格": spec}, ensure_ascii=False), img),
                )
                sku_id = cur.fetchone()[0]
                if first_sku is None:
                    first_sku = sku_id
                stock = random.randint(30, 200)
                cur.execute(
                    "INSERT INTO inventories (sku_id, total_stock, available_stock, locked_stock, sold_stock)"
                    " VALUES (%s, %s, %s, 0, %s)", (sku_id, stock, stock, random.randint(0, 20)))
            created += 1
    conn.commit()
    cur.execute("SELECT count(*) FROM products")
    total = cur.fetchone()[0]
    print(json.dumps({"created": created, "productsTotal": total}, ensure_ascii=False))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
