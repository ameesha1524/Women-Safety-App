import sqlite3

def seed():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Clear existing data for a clean test
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM ratings")

    # 1. CREATE WORKER NODES
    # Format: (username, password, role, shield_id, category, house_code)
    workers = [
        ('danger_dan', 'pass123', 'worker', 'SH-RED1', 'Delivery', 'NONE'),
        ('neutral_sam', 'pass123', 'worker', 'SH-BLU2', 'Plumbing', 'NONE'),
        ('pro_clara', 'pass123', 'worker', 'SH-GOLD', 'Uber', 'NONE')
    ]
    c.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", workers)

    # 2. SEED WORKER 1: HIGH RISK (SH-RED1)
    # Triggers 'High Risk' status and red heatmap points
    red_ratings = [
        ('SH-RED1', 'user_a', 1, 'Extremely aggressive behavior, felt unsafe.', 'High Risk', 12.9710, 79.1580),
        ('SH-RED1', 'user_b', 2, 'Made me feel very uncomfortable during the dropoff.', 'High Risk', 12.9720, 79.1600)
    ]
    c.executemany("INSERT INTO ratings VALUES (?, ?, ?, ?, ?, ?, ?)", red_ratings)

    # 3. SEED WORKER 2: LOW RISK (SH-BLU2)
    # Triggers 'Suspicious' or 'Verified Safe'
    blue_ratings = [
        ('SH-BLU2', 'user_c', 3, 'Decent work but was quite late.', 'Suspicious', 12.9680, 79.1550),
        ('SH-BLU2', 'user_d', 4, 'Good service, no issues.', 'Verified Safe', 12.9690, 79.1560)
    ]
    c.executemany("INSERT INTO ratings VALUES (?, ?, ?, ?, ?, ?, ?)", blue_ratings)

    # 4. SEED WORKER 3: SHIELD CERTIFIED (SH-GOLD)
    # Needs 50+ reviews, >4.5 Avg, 0 High Risk flags
    for i in range(55):
        rating = 5 if i % 10 != 0 else 4 # Mix of 5s and 4s for a realistic 4.9 avg
        c.execute("INSERT INTO ratings VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('SH-GOLD', f'tester_{i}', rating, 'Excellent professional service.', 'Verified Safe', 12.9700, 79.1500))

    conn.commit()
    conn.close()
    print("Shield Network Seeded Successfully.")

if __name__ == "__main__":
    seed()