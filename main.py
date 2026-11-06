import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Учёт шаурмичной", page_icon="🌯", layout="wide")

DB_PATH = Path(__file__).with_name("recipes.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


DEFAULT_INGREDIENTS = [
    ("Курица", "кг", 180.0, 50.0),
    ("Лаваш", "шт", 8.0, 100.0),
    ("Капуста", "кг", 35.0, 10.0),
    ("Огурец", "кг", 70.0, 10.0),
    ("Помидор", "кг", 80.0, 10.0),
    ("Соус", "кг", 100.0, 5.0),
]

DEFAULT_SETTINGS = {
    "rent": 15000.0,
    "electricity": 3000.0,
    "water": 500.0,
    "gas": 1500.0,
    "other_utilities": 0.0,
    "other_expenses": 0.0,
    "employees": 2,
    "salary": 15000.0,
    "packaging": 3.0,
    "napkins": 1.0,
    "waste_percent": 5.0,
    "global_markup": 100.0,
}


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Шаурма'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recipe_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                ingredient TEXT NOT NULL,
                quantity REAL NOT NULL,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                unit TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                purchased REAL NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                name TEXT PRIMARY KEY,
                value REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS menu (
                name TEXT PRIMARY KEY,
                sales REAL NOT NULL DEFAULT 0,
                markup REAL
            )
        """)
        if conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0:
            cur = conn.execute(
                "INSERT INTO recipes(name, category) VALUES (?, ?)",
                ("Классическая", "Шаурма"),
            )
            rid = cur.lastrowid
            conn.executemany(
                "INSERT INTO recipe_ingredients(recipe_id, ingredient, quantity) VALUES (?, ?, ?)",
                [(rid, n, q) for n, q in [
                    ("Курица", 0.15), ("Лаваш", 1), ("Капуста", 0.08),
                    ("Огурец", 0.04), ("Помидор", 0.04), ("Соус", 0.03)
                ]],
            )
        if conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO ingredients(name, unit, price, purchased) VALUES (?, ?, ?, ?)",
                DEFAULT_INGREDIENTS,
            )
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(name, value) VALUES (?, ?)",
                (key, value),
            )


def load_settings():
    with get_connection() as conn:
        values = dict(conn.execute("SELECT name, value FROM settings").fetchall())
    result = DEFAULT_SETTINGS.copy()
    result.update(values)
    result["employees"] = int(result["employees"])
    return result


def save_settings(values):
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO settings(name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            [(k, float(v)) for k, v in values.items()],
        )


def load_ingredients():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, unit, price, purchased FROM ingredients ORDER BY id"
        ).fetchall()
    return pd.DataFrame(rows, columns=["Название", "Единица", "Цена закупки", "Закуплено"])


def save_ingredients(df):
    rows = []
    for _, r in df.iterrows():
        name = str(r.get("Название", "")).strip()
        unit = str(r.get("Единица", "")).strip()
        price = pd.to_numeric(r.get("Цена закупки", 0), errors="coerce")
        purchased = pd.to_numeric(r.get("Закуплено", 0), errors="coerce")
        if name and unit:
            rows.append((name, unit, max(0.0, float(price) if pd.notna(price) else 0.0),
                         max(0.0, float(purchased) if pd.notna(purchased) else 0.0)))
    with get_connection() as conn:
        conn.execute("DELETE FROM ingredients")
        conn.executemany(
            "INSERT INTO ingredients(name, unit, price, purchased) VALUES (?, ?, ?, ?)",
            rows,
        )


def load_recipes():
    with get_connection() as conn:
        return conn.execute("""
            SELECT r.id, r.name, r.category, ri.ingredient, ri.quantity
            FROM recipes r
            LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
            ORDER BY r.id, ri.id
        """).fetchall()


def save_recipe(name, category, df, recipe_id=None):
    name = str(name).strip()
    if not name:
        raise ValueError("Укажи название блюда.")
    rows = []
    for _, r in df.iterrows():
        ingredient = str(r.get("Ингредиент", "")).strip()
        qty = pd.to_numeric(r.get("Количество", 0), errors="coerce")
        if ingredient and pd.notna(qty) and float(qty) > 0:
            rows.append((ingredient, float(qty)))
    if not rows:
        raise ValueError("Добавь хотя бы один ингредиент с количеством больше нуля.")
    with get_connection() as conn:
        if recipe_id is None:
            cur = conn.execute(
                "INSERT INTO recipes(name, category) VALUES (?, ?)", (name, category)
            )
            recipe_id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE recipes SET name=?, category=? WHERE id=?",
                (name, category, recipe_id),
            )
            conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (recipe_id,))
        conn.executemany(
            "INSERT INTO recipe_ingredients(recipe_id, ingredient, quantity) VALUES (?, ?, ?)",
            [(recipe_id, n, q) for n, q in rows],
        )


def load_menu(names):
    with get_connection() as conn:
        saved = {n: (s, m) for n, s, m in conn.execute(
            "SELECT name, sales, markup FROM menu"
        ).fetchall()}
    return pd.DataFrame([
        {"Название": n, "Количество продаж": saved.get(n, (0, None))[0],
         "Индивидуальная наценка (%)": saved.get(n, (0, None))[1]}
        for n in names
    ], columns=["Название", "Количество продаж", "Индивидуальная наценка (%)"])


def save_menu(df):
    rows = []
    for _, r in df.iterrows():
        name = str(r.get("Название", "")).strip()
        if not name:
            continue
        sales = pd.to_numeric(r.get("Количество продаж", 0), errors="coerce")
        markup = pd.to_numeric(r.get("Индивидуальная наценка (%)"), errors="coerce")
        rows.append((name, max(0.0, float(sales) if pd.notna(sales) else 0.0),
                     float(markup) if pd.notna(markup) else None))
    with get_connection() as conn:
        conn.execute("DELETE FROM menu")
        conn.executemany(
            "INSERT INTO menu(name, sales, markup) VALUES (?, ?, ?)", rows
        )


def delete_recipe(recipe_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (recipe_id,))
        conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))


def copy_recipe(recipe_id):
    with get_connection() as conn:
        item = conn.execute(
            "SELECT name, category FROM recipes WHERE id=?", (recipe_id,)
        ).fetchone()
        if not item:
            return
        cur = conn.execute(
            "INSERT INTO recipes(name, category) VALUES (?, ?)",
            (item[0] + " — копия", item[1]),
        )
        conn.execute("""
            INSERT INTO recipe_ingredients(recipe_id, ingredient, quantity)
            SELECT ?, ingredient, quantity FROM recipe_ingredients WHERE recipe_id=?
        """, (cur.lastrowid, recipe_id))


init_db()
st.title("🌯 Финансовый учёт шаурмичной")
st.caption("Закупки, рецепты, себестоимость, наценка, продажи и прибыль")
st.info(
    "Важно: изменяй поля, затем нажимай соответствующую кнопку «Сохранить». "
    "Теперь введённые значения записываются в recipes.db и не сбрасываются при обновлении страницы."
)

settings = load_settings()

# Финансовые настройки — одна форма, чтобы ввод не прерывался перезапуском страницы.
st.header("1. Постоянные расходы и параметры")
with st.form("settings_form"):
    a, b, c = st.columns(3)
    with a:
        rent = st.number_input("Аренда в месяц (грн)", min_value=0.0, value=float(settings["rent"]), key="s_rent")
        electricity = st.number_input("Электричество (грн)", min_value=0.0, value=float(settings["electricity"]), key="s_electricity")
        water = st.number_input("Вода (грн)", min_value=0.0, value=float(settings["water"]), key="s_water")
        gas = st.number_input("Газ (грн)", min_value=0.0, value=float(settings["gas"]), key="s_gas")
    with b:
        other_utilities = st.number_input("Другие коммунальные (грн)", min_value=0.0, value=float(settings["other_utilities"]), key="s_other_utilities")
        other_expenses = st.number_input("Прочие расходы (грн)", min_value=0.0, value=float(settings["other_expenses"]), key="s_other_expenses")
        employees = st.number_input("Количество работников", min_value=0, max_value=100, value=int(settings["employees"]), step=1, key="s_employees")
        salary = st.number_input("Зарплата одного работника (грн)", min_value=0.0, value=float(settings["salary"]), key="s_salary")
    with c:
        packaging = st.number_input("Упаковка на одну порцию (грн)", min_value=0.0, value=float(settings["packaging"]), key="s_packaging")
        napkins = st.number_input("Салфетки и пакеты на порцию (грн)", min_value=0.0, value=float(settings["napkins"]), key="s_napkins")
        waste_percent = st.number_input("Потери продуктов (%)", min_value=0.0, max_value=100.0, value=float(settings["waste_percent"]), key="s_waste")
        global_markup = st.number_input("Общая наценка для всех блюд (%)", min_value=0.0, max_value=1000.0, value=float(settings["global_markup"]), step=5.0, key="s_markup")
    save_settings_button = st.form_submit_button("💾 Сохранить параметры", type="primary")
if save_settings_button:
    save_settings({
        "rent": rent, "electricity": electricity, "water": water, "gas": gas,
        "other_utilities": other_utilities, "other_expenses": other_expenses,
        "employees": employees, "salary": salary, "packaging": packaging,
        "napkins": napkins, "waste_percent": waste_percent,
        "global_markup": global_markup,
    })
    st.success("Параметры сохранены.")

st.divider()
st.header("2. Закупка ингредиентов")
st.caption("Цена указывается за единицу: например, курица — грн/кг, лаваш — грн/шт.")
ingredients_df = load_ingredients()
with st.form("ingredients_form"):
    edited_ingredients = st.data_editor(
        ingredients_df, num_rows="dynamic", use_container_width=True,
        key="ingredients_editor_v2",
        column_config={
            "Название": st.column_config.TextColumn("Название"),
            "Единица": st.column_config.TextColumn("Единица"),
            "Цена закупки": st.column_config.NumberColumn("Цена за единицу (грн)", min_value=0.0, format="%.2f"),
            "Закуплено": st.column_config.NumberColumn("Закуплено за месяц", min_value=0.0),
        },
    )
    save_ingredients_button = st.form_submit_button("💾 Сохранить закупки", type="primary")
if save_ingredients_button:
    save_ingredients(edited_ingredients)
    st.success("Закупки сохранены.")
    st.rerun()

ingredients = load_ingredients()
if not ingredients.empty:
    ingredients["Стоимость закупки"] = ingredients["Цена закупки"] * ingredients["Закуплено"]
    st.metric("Всего закуплено на", f"{ingredients['Стоимость закупки'].sum():,.2f} грн")
ingredient_names = ingredients["Название"].dropna().astype(str).str.strip().tolist()
ingredient_names = list(dict.fromkeys([x for x in ingredient_names if x]))

st.divider()
st.header("3. Управление рецептами")
with st.expander("➕ Добавить рецепт"):
    with st.form("add_recipe_form", clear_on_submit=True):
        new_name = st.text_input("Название блюда", placeholder="Например, Сырная шаурма")
        new_category = st.selectbox("Категория", ["Шаурма", "Комбо", "Напитки", "Другое"])
        if ingredient_names:
            new_rows = st.data_editor(
                pd.DataFrame({"Ингредиент": [ingredient_names[0]], "Количество": [0.0]}),
                num_rows="dynamic", use_container_width=True, key="new_recipe_editor_v2",
                column_config={
                    "Ингредиент": st.column_config.SelectboxColumn("Ингредиент", options=ingredient_names, required=True),
                    "Количество": st.column_config.NumberColumn("Количество (в единицах закупки)", min_value=0.0),
                },
            )
        else:
            new_rows = pd.DataFrame(columns=["Ингредиент", "Количество"])
            st.warning("Сначала добавь ингредиенты в закупки.")
        add_recipe_button = st.form_submit_button("Сохранить рецепт", type="primary")
    if add_recipe_button:
        try:
            save_recipe(new_name, new_category, new_rows)
            st.success(f"Рецепт «{new_name}» сохранён.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

recipe_rows = load_recipes()
recipe_ids = list(dict.fromkeys(r[0] for r in recipe_rows))
recipe_labels = {r[0]: f"{r[1]} (#{r[0]})" for r in recipe_rows}

if recipe_ids:
    with st.expander("✏️ Редактировать, копировать или удалить рецепт"):
        selected_id = st.selectbox("Выбери рецепт", recipe_ids, format_func=lambda x: recipe_labels[x], key="selected_recipe_v2")
        selected_rows = [r for r in recipe_rows if r[0] == selected_id]
        cats = ["Шаурма", "Комбо", "Напитки", "Другое"]
        with st.form(f"edit_recipe_form_{selected_id}"):
            edit_name = st.text_input("Название", value=selected_rows[0][1], key=f"edit_name_v2_{selected_id}")
            edit_category = st.selectbox("Категория", cats, index=cats.index(selected_rows[0][2]) if selected_rows[0][2] in cats else 0, key=f"edit_cat_v2_{selected_id}")
            edit_df = pd.DataFrame(
                [{"Ингредиент": r[3], "Количество": r[4]} for r in selected_rows if r[3] is not None],
                columns=["Ингредиент", "Количество"],
            )
            if edit_df.empty:
                edit_df = pd.DataFrame({"Ингредиент": [ingredient_names[0] if ingredient_names else ""], "Количество": [0.0]})
            edited_recipe = st.data_editor(
                edit_df, num_rows="dynamic", use_container_width=True,
                key=f"edit_recipe_editor_v2_{selected_id}",
                column_config={
                    "Ингредиент": st.column_config.SelectboxColumn("Ингредиент", options=ingredient_names),
                    "Количество": st.column_config.NumberColumn("Количество", min_value=0.0),
                },
            )
            edit_button = st.form_submit_button("💾 Сохранить изменения", type="primary")
        if edit_button:
            try:
                save_recipe(edit_name, edit_category, edited_recipe, recipe_id=selected_id)
                st.success("Рецепт сохранён.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
        x, y = st.columns(2)
        with x:
            if st.button("Копировать рецепт", key=f"copy_v2_{selected_id}"):
                copy_recipe(selected_id)
                st.success("Копия создана.")
                st.rerun()
        with y:
            if st.button("Удалить рецепт", key=f"delete_v2_{selected_id}"):
                delete_recipe(selected_id)
                st.success("Рецепт удалён.")
                st.rerun()

recipe_rows = load_recipes()
recipe_ids = list(dict.fromkeys(r[0] for r in recipe_rows))
recipe_names = []
recipe_cost_map = {}
recipe_table = []
cost_map = dict(zip(ingredients["Название"].astype(str).str.strip(), ingredients["Цена закупки"])) if not ingredients.empty else {}

for rid in recipe_ids:
    rows = [r for r in recipe_rows if r[0] == rid]
    name, category = rows[0][1], rows[0][2]
    recipe_names.append(name)
    cost = 0.0
    for r in rows:
        if r[3] is not None:
            cost += float(r[4] or 0) * float(cost_map.get(r[3], 0))
            recipe_table.append({"ID": rid, "Блюдо": name, "Категория": category, "Ингредиент": r[3], "Количество": r[4]})
    recipe_cost_map[name] = cost

if recipe_table:
    st.subheader("Список рецептов")
    st.dataframe(pd.DataFrame(recipe_table), use_container_width=True)

st.divider()
st.header("4. Продажи, индивидуальная наценка и расчёт")
st.caption("Оставь индивидуальную наценку пустой, чтобы применялась общая наценка.")
menu_df = load_menu(recipe_names)
with st.form("menu_form"):
    edited_menu = st.data_editor(
        menu_df, num_rows="dynamic", use_container_width=True, key="menu_editor_v2",
        column_config={
            "Название": st.column_config.SelectboxColumn("Название блюда", options=recipe_names),
            "Количество продаж": st.column_config.NumberColumn("Количество продаж", min_value=0, step=1),
            "Индивидуальная наценка (%)": st.column_config.NumberColumn("Своя наценка (%) — необязательно", min_value=0.0, max_value=1000.0, format="%.1f"),
        },
    )
    save_menu_button = st.form_submit_button("💾 Сохранить продажи и наценки", type="primary")
if save_menu_button:
    save_menu(edited_menu)
    st.success("Продажи и наценки сохранены.")
    st.rerun()

menu = load_menu(recipe_names)
if menu.empty:
    menu = pd.DataFrame(columns=["Название", "Количество продаж", "Индивидуальная наценка (%)"])
menu["Продукты"] = menu["Название"].map(recipe_cost_map).fillna(0)
menu["Расходники"] = float(settings["packaging"]) + float(settings["napkins"])
menu["Себестоимость"] = menu["Продукты"] * (1 + float(settings["waste_percent"]) / 100) + menu["Расходники"]
individual = pd.to_numeric(menu["Индивидуальная наценка (%)"], errors="coerce")
menu["Применённая наценка (%)"] = individual.fillna(float(settings["global_markup"]))
menu["Цена продажи"] = menu["Себестоимость"] * (1 + menu["Применённая наценка (%)"] / 100)
menu["Прибыль с единицы"] = menu["Цена продажи"] - menu["Себестоимость"]
menu["Количество продаж"] = pd.to_numeric(menu["Количество продаж"], errors="coerce").fillna(0)
menu["Выручка"] = menu["Цена продажи"] * menu["Количество продаж"]
menu["Переменные расходы"] = menu["Себестоимость"] * menu["Количество продаж"]
menu["Валовая прибыль"] = menu["Выручка"] - menu["Переменные расходы"]

fixed_costs = (
    float(settings["rent"]) + float(settings["electricity"]) + float(settings["water"])
    + float(settings["gas"]) + float(settings["other_utilities"])
    + float(settings["other_expenses"]) + int(settings["employees"]) * float(settings["salary"])
)
revenue = menu["Выручка"].sum()
variable_costs = menu["Переменные расходы"].sum()
profit = revenue - variable_costs - fixed_costs
units = menu["Количество продаж"].sum()
gross_profit = revenue - variable_costs
average_margin = gross_profit / units if units > 0 else 0
break_even = fixed_costs / average_margin if average_margin > 0 else 0

st.subheader("5. Финансовый результат")
a, b, c = st.columns(3)
a.metric("Выручка", f"{revenue:,.2f} грн")
b.metric("Переменные расходы", f"{variable_costs:,.2f} грн")
c.metric("Постоянные расходы", f"{fixed_costs:,.2f} грн")
if profit > 0:
    st.success(f"ЧИСТАЯ ПРИБЫЛЬ: {profit:,.2f} грн")
elif profit < 0:
    st.error(f"УБЫТОК: {profit:,.2f} грн")
else:
    st.warning("РАБОТА В НОЛЬ")
a, b, c = st.columns(3)
a.metric("Продано порций", f"{units:,.0f} шт.")
b.metric("Прибыль до постоянных расходов", f"{gross_profit:,.2f} грн")
c.metric("Рентабельность", f"{profit / revenue * 100:.2f}%" if revenue else "0%")
st.metric("Точка безубыточности", f"{break_even:,.0f} шт.")

st.subheader("Экономика каждой позиции")
display_cols = [
    "Название", "Продукты", "Расходники", "Себестоимость",
    "Применённая наценка (%)", "Цена продажи", "Прибыль с единицы",
    "Количество продаж", "Выручка", "Переменные расходы", "Валовая прибыль",
]
if not menu.empty:
    st.dataframe(
        menu[display_cols].style.format({
            "Продукты": "{:,.2f}", "Расходники": "{:,.2f}",
            "Себестоимость": "{:,.2f}", "Применённая наценка (%)": "{:,.1f}%",
            "Цена продажи": "{:,.2f}", "Прибыль с единицы": "{:,.2f}",
            "Выручка": "{:,.2f}", "Переменные расходы": "{:,.2f}",
            "Валовая прибыль": "{:,.2f}",
        }),
        use_container_width=True,
    )

st.subheader("Расходы предприятия")
expenses = pd.DataFrame({
    "Статья": ["Аренда", "Электричество", "Вода", "Газ", "Другие коммунальные",
               "Прочие расходы", "Зарплаты", "Продукты и расходники"],
    "Сумма (грн)": [
        settings["rent"], settings["electricity"], settings["water"], settings["gas"],
        settings["other_utilities"], settings["other_expenses"],
        settings["employees"] * settings["salary"], variable_costs,
    ],
})
st.dataframe(expenses, use_container_width=True)
