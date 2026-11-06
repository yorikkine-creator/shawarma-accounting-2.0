import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Учёт шаурмичной",
    page_icon="🌯",
    layout="wide",
)

DB_PATH = Path(__file__).with_name("recipes.db")


# -----------------------------
# БАЗА ДАННЫХ РЕЦЕПТОВ
# -----------------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_recipe_database():
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
                FOREIGN KEY (recipe_id) REFERENCES recipes(id)
                    ON DELETE CASCADE
            )
        """)

        # Переносим исходный пример рецепта в базу только при первом запуске.
        count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        if count == 0:
            cursor = conn.execute(
                "INSERT INTO recipes (name, category) VALUES (?, ?)",
                ("Классическая", "Шаурма"),
            )
            recipe_id = cursor.lastrowid
            conn.executemany(
                """INSERT INTO recipe_ingredients
                   (recipe_id, ingredient, quantity) VALUES (?, ?, ?)""",
                [
                    (recipe_id, "Курица", 0.15),
                    (recipe_id, "Лаваш", 1.0),
                    (recipe_id, "Капуста", 0.08),
                    (recipe_id, "Огурец", 0.04),
                    (recipe_id, "Помидор", 0.04),
                    (recipe_id, "Соус", 0.03),
                ],
            )


def load_recipes():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT r.id, r.name, r.category,
                   ri.ingredient, ri.quantity
            FROM recipes r
            LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
            ORDER BY r.id, ri.id
        """).fetchall()
    return rows


def save_recipe(name, category, ingredients_df, recipe_id=None):
    clean_rows = []
    for _, row in ingredients_df.iterrows():
        ingredient = str(row.get("Ингредиент", "")).strip()
        quantity = pd.to_numeric(row.get("Количество", 0), errors="coerce")
        if ingredient and pd.notna(quantity) and float(quantity) > 0:
            clean_rows.append((ingredient, float(quantity)))

    if not name.strip():
        raise ValueError("Укажи название рецепта.")
    if not clean_rows:
        raise ValueError("Добавь хотя бы один ингредиент с количеством больше нуля.")

    with get_connection() as conn:
        if recipe_id is None:
            cursor = conn.execute(
                "INSERT INTO recipes (name, category) VALUES (?, ?)",
                (name.strip(), category),
            )
            recipe_id = cursor.lastrowid
        else:
            conn.execute(
                "UPDATE recipes SET name = ?, category = ? WHERE id = ?",
                (name.strip(), category, recipe_id),
            )
            conn.execute(
                "DELETE FROM recipe_ingredients WHERE recipe_id = ?",
                (recipe_id,),
            )

        conn.executemany(
            """INSERT INTO recipe_ingredients
               (recipe_id, ingredient, quantity) VALUES (?, ?, ?)""",
            [(recipe_id, ingredient, quantity)
             for ingredient, quantity in clean_rows],
        )


def delete_recipe(recipe_id):
    with get_connection() as conn:
        # Явно удаляем состав: это работает и со старой версией таблицы.
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE recipe_id = ?",
            (recipe_id,),
        )
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


def copy_recipe(recipe_id):
    with get_connection() as conn:
        recipe = conn.execute(
            "SELECT name, category FROM recipes WHERE id = ?",
            (recipe_id,),
        ).fetchone()
        if not recipe:
            return
        cursor = conn.execute(
            "INSERT INTO recipes (name, category) VALUES (?, ?)",
            (recipe[0] + " — копия", recipe[1]),
        )
        new_id = cursor.lastrowid
        conn.execute("""
            INSERT INTO recipe_ingredients (recipe_id, ingredient, quantity)
            SELECT ?, ingredient, quantity
            FROM recipe_ingredients WHERE recipe_id = ?
        """, (new_id, recipe_id))


init_recipe_database()

st.title("🌯 Финансовый учёт шаурмичной")
st.caption("Закупки, рецепты, себестоимость, наценка, продажи и прибыль")


# -----------------------------
# 1. ПОСТОЯННЫЕ РАСХОДЫ
# -----------------------------
st.header("1. Постоянные расходы")
c1, c2, c3 = st.columns(3)
with c1:
    rent = st.number_input("Аренда в месяц (грн)", min_value=0.0, value=15000.0)
    electricity = st.number_input("Электричество (грн)", min_value=0.0, value=3000.0)
with c2:
    water = st.number_input("Вода (грн)", min_value=0.0, value=500.0)
    gas = st.number_input("Газ (грн)", min_value=0.0, value=1500.0)
with c3:
    other_utilities = st.number_input("Другие коммунальные (грн)", min_value=0.0)
    other_expenses = st.number_input("Прочие расходы (грн)", min_value=0.0)


# -----------------------------
# 2. СОТРУДНИКИ
# -----------------------------
st.header("2. Сотрудники")
c1, c2 = st.columns(2)
with c1:
    employees = st.number_input("Количество работников", 0, 100, 2)
with c2:
    salary = st.number_input("Зарплата одного работника (грн)", min_value=0.0, value=15000.0)
salary_total = employees * salary


# -----------------------------
# 3. ЗАКУПКА ИНГРЕДИЕНТОВ
# -----------------------------
st.header("3. Закупка ингредиентов")
st.info(
    "Указывай цену за единицу измерения: например, курица — грн за кг, "
    "лаваш — грн за штуку. В рецепте количество указывается в тех же единицах."
)

default_ingredients = pd.DataFrame(
    [
        ["Курица", "кг", 180.0, 50.0],
        ["Лаваш", "шт", 8.0, 100.0],
        ["Капуста", "кг", 35.0, 10.0],
        ["Огурец", "кг", 70.0, 10.0],
        ["Помидор", "кг", 80.0, 10.0],
        ["Соус", "кг", 100.0, 5.0],
    ],
    columns=["Название", "Единица", "Цена закупки", "Закуплено"],
)

if "ingredients_data" not in st.session_state:
    st.session_state.ingredients_data = default_ingredients.copy()

ingredients = st.data_editor(
    st.session_state.ingredients_data,
    num_rows="dynamic",
    use_container_width=True,
    key="ingredients_editor",
    column_config={
        "Название": st.column_config.TextColumn("Название"),
        "Единица": st.column_config.TextColumn("Единица"),
        "Цена закупки": st.column_config.NumberColumn(
            "Цена за единицу (грн)", min_value=0.0, format="%.2f"
        ),
        "Закуплено": st.column_config.NumberColumn(
            "Закуплено за месяц", min_value=0.0
        ),
    },
)
st.session_state.ingredients_data = ingredients.copy()

ingredients["Цена закупки"] = pd.to_numeric(
    ingredients["Цена закупки"], errors="coerce"
).fillna(0)
ingredients["Закуплено"] = pd.to_numeric(
    ingredients["Закуплено"], errors="coerce"
).fillna(0)
ingredients["Стоимость закупки"] = (
    ingredients["Цена закупки"] * ingredients["Закуплено"]
)

st.metric("Всего закуплено на", f"{ingredients['Стоимость закупки'].sum():,.2f} грн")
ingredient_names = (
    ingredients["Название"].dropna().astype(str).str.strip().tolist()
)
ingredient_names = list(dict.fromkeys([x for x in ingredient_names if x]))


# -----------------------------
# 4. УПРАВЛЕНИЕ РЕЦЕПТАМИ
# -----------------------------
st.header("4. Управление рецептами")
st.caption("Рецепты сохраняются в локальной базе recipes.db.")

with st.expander("➕ Добавить рецепт", expanded=False):
    with st.form("add_recipe_form"):
        new_name = st.text_input("Название блюда", placeholder="Например, Сырная шаурма")
        new_category = st.selectbox(
            "Категория", ["Шаурма", "Комбо", "Напитки", "Другое"]
        )
        if ingredient_names:
            new_recipe_rows = pd.DataFrame(
                {"Ингредиент": [ingredient_names[0]], "Количество": [0.0]}
            )
            new_recipe_rows = st.data_editor(
                new_recipe_rows,
                num_rows="dynamic",
                use_container_width=True,
                key="new_recipe_rows",
                column_config={
                    "Ингредиент": st.column_config.SelectboxColumn(
                        "Ингредиент", options=ingredient_names, required=True
                    ),
                    "Количество": st.column_config.NumberColumn(
                        "Количество (в единицах закупки)", min_value=0.0
                    ),
                },
            )
        else:
            new_recipe_rows = pd.DataFrame(columns=["Ингредиент", "Количество"])
            st.warning("Сначала добавь ингредиенты в раздел закупок.")
        submitted = st.form_submit_button("Сохранить рецепт", type="primary")
        if submitted:
            try:
                save_recipe(new_name, new_category, new_recipe_rows)
                st.success(f"Рецепт «{new_name}» сохранён.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

recipe_rows = load_recipes()
recipe_ids = list(dict.fromkeys(row[0] for row in recipe_rows))
recipe_labels = {
    row[0]: f"{row[1]} (#{row[0]})"
    for row in recipe_rows
}
recipe_costs = {}
recipe_table_rows = []

for recipe_id in recipe_ids:
    rows_for_recipe = [r for r in recipe_rows if r[0] == recipe_id]
    name = rows_for_recipe[0][1]
    category = rows_for_recipe[0][2]
    for row in rows_for_recipe:
        if row[3] is not None:
            recipe_table_rows.append(
                {
                    "ID": recipe_id,
                    "Блюдо": name,
                    "Категория": category,
                    "Ингредиент": row[3],
                    "Количество": row[4],
                }
            )

if recipe_ids:
    with st.expander("✏️ Редактировать, копировать или удалить рецепт"):
        selected_recipe_id = st.selectbox(
            "Выбери рецепт",
            recipe_ids,
            format_func=lambda x: recipe_labels[x],
            key="selected_recipe_id",
        )
        selected_rows = [r for r in recipe_rows if r[0] == selected_recipe_id]
        selected_name = selected_rows[0][1]
        selected_category = selected_rows[0][2]
        edit_name = st.text_input(
            "Название", value=selected_name, key=f"edit_name_{selected_recipe_id}"
        )
        categories = ["Шаурма", "Комбо", "Напитки", "Другое"]
        edit_category = st.selectbox(
            "Категория",
            categories,
            index=categories.index(selected_category)
            if selected_category in categories else 0,
            key=f"edit_category_{selected_recipe_id}",
        )
        edit_data = pd.DataFrame(
            [
                {"Ингредиент": r[3], "Количество": r[4]}
                for r in selected_rows if r[3] is not None
            ],
            columns=["Ингредиент", "Количество"],
        )
        if edit_data.empty:
            edit_data = pd.DataFrame(
                {"Ингредиент": [ingredient_names[0] if ingredient_names else ""],
                 "Количество": [0.0]}
            )
        edit_data = st.data_editor(
            edit_data,
            num_rows="dynamic",
            use_container_width=True,
            key=f"edit_rows_{selected_recipe_id}",
            column_config={
                "Ингредиент": st.column_config.SelectboxColumn(
                    "Ингредиент", options=ingredient_names
                ),
                "Количество": st.column_config.NumberColumn(
                    "Количество", min_value=0.0
                ),
            },
        )
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Сохранить изменения", key=f"save_{selected_recipe_id}"):
                try:
                    save_recipe(
                        edit_name, edit_category, edit_data,
                        recipe_id=selected_recipe_id
                    )
                    st.success("Изменения сохранены.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with b2:
            if st.button("Копировать рецепт", key=f"copy_{selected_recipe_id}"):
                copy_recipe(selected_recipe_id)
                st.success("Копия создана.")
                st.rerun()
        with b3:
            if st.button("Удалить рецепт", key=f"delete_{selected_recipe_id}"):
                delete_recipe(selected_recipe_id)
                st.success("Рецепт удалён.")
                st.rerun()

if recipe_table_rows:
    st.subheader("Список рецептов")
    st.dataframe(pd.DataFrame(recipe_table_rows), use_container_width=True)
else:
    st.info("Рецептов пока нет. Добавь первый рецепт выше.")


# -----------------------------
# 5. РАСХОДНИКИ И ПОТЕРИ
# -----------------------------
st.header("5. Расходники и потери")
c1, c2, c3 = st.columns(3)
with c1:
    packaging = st.number_input("Упаковка на одну порцию (грн)", min_value=0.0, value=3.0)
with c2:
    napkins = st.number_input("Салфетки и пакеты на одну порцию (грн)", min_value=0.0, value=1.0)
with c3:
    waste_percent = st.number_input("Потери продуктов (%)", 0.0, 100.0, 5.0)


# -----------------------------
# 6. НАЦЕНКА И МЕНЮ
# -----------------------------
st.header("6. Наценка и меню")
global_markup = st.number_input(
    "Общая наценка для всех блюд (%)",
    min_value=0.0,
    max_value=1000.0,
    value=100.0,
    step=5.0,
    help="Используется для всех блюд, у которых не задана индивидуальная наценка.",
)

st.caption(
    "В таблице можно задать отдельную наценку для каждой позиции. "
    "Если поле оставить пустым, будет применена общая наценка."
)

recipe_names = []
for recipe_id in recipe_ids:
    rows_for_recipe = [r for r in recipe_rows if r[0] == recipe_id]
    if rows_for_recipe:
        recipe_names.append(rows_for_recipe[0][1])

if "menu_data" not in st.session_state:
    initial_names = recipe_names if recipe_names else ["Классическая"]
    st.session_state.menu_data = pd.DataFrame(
        {
            "Название": initial_names,
            "Количество продаж": [0 for _ in initial_names],
            "Индивидуальная наценка (%)": [None for _ in initial_names],
        }
    )

# Добавляем в меню новые рецепты, не удаляя уже внесённые строки.
menu_existing = st.session_state.menu_data.copy()
for recipe_name in recipe_names:
    if recipe_name not in menu_existing["Название"].astype(str).tolist():
        menu_existing.loc[len(menu_existing)] = [recipe_name, 0, None]

menu = st.data_editor(
    menu_existing,
    num_rows="dynamic",
    use_container_width=True,
    key="menu_editor",
    column_config={
        "Название": st.column_config.SelectboxColumn(
            "Название блюда", options=list(dict.fromkeys(recipe_names))
        ),
        "Количество продаж": st.column_config.NumberColumn(
            "Количество продаж", min_value=0, step=1
        ),
        "Индивидуальная наценка (%)": st.column_config.NumberColumn(
            "Своя наценка (%) — необязательно",
            min_value=0.0,
            max_value=1000.0,
            format="%.1f",
        ),
    },
)
st.session_state.menu_data = menu.copy()


# -----------------------------
# 7. РАСЧЁТ СЕБЕСТОИМОСТИ И ЦЕН
# -----------------------------
valid_ingredients = ingredients.dropna(subset=["Название"]).copy()
cost_map = dict(
    zip(
        valid_ingredients["Название"].astype(str).str.strip(),
        valid_ingredients["Цена закупки"],
    )
)

recipe_cost_map = {}
for recipe_id in recipe_ids:
    rows_for_recipe = [r for r in recipe_rows if r[0] == recipe_id]
    name = rows_for_recipe[0][1]
    product_cost = 0.0
    for row in rows_for_recipe:
        ingredient = row[3]
        quantity = row[4]
        if ingredient is not None:
            product_cost += float(quantity or 0) * float(cost_map.get(ingredient, 0))
    recipe_cost_map[name] = product_cost

menu = menu.dropna(subset=["Название"]).copy()
menu["Название"] = menu["Название"].astype(str)
menu["Количество продаж"] = pd.to_numeric(
    menu["Количество продаж"], errors="coerce"
).fillna(0)
menu["Продукты"] = menu["Название"].map(recipe_cost_map).fillna(0)
menu["Расходники"] = packaging + napkins
menu["Себестоимость"] = (
    menu["Продукты"] * (1 + waste_percent / 100) + menu["Расходники"]
)

individual_markup = pd.to_numeric(
    menu["Индивидуальная наценка (%)"], errors="coerce"
)
menu["Применённая наценка (%)"] = individual_markup.fillna(global_markup)
menu["Цена продажи"] = (
    menu["Себестоимость"] * (1 + menu["Применённая наценка (%)"] / 100)
)
menu["Прибыль с единицы"] = menu["Цена продажи"] - menu["Себестоимость"]
menu["Выручка"] = menu["Цена продажи"] * menu["Количество продаж"]
menu["Переменные расходы"] = (
    menu["Себестоимость"] * menu["Количество продаж"]
)
menu["Валовая прибыль"] = menu["Выручка"] - menu["Переменные расходы"]


# -----------------------------
# 8. КНОПКА ПЕРЕСЧЁТА
# -----------------------------
if st.button("🔄 Пересчитать себестоимость и затраты", type="primary"):
    st.session_state["recalculated"] = True
    st.success("Расчёты обновлены по текущим закупочным ценам, рецептам и наценкам.")

st.caption(
    "Streamlit также пересчитывает показатели автоматически при изменении данных. "
    "Кнопка выше позволяет явно подтвердить пересчёт."
)


# -----------------------------
# 9. ОБЩИЕ ИТОГИ
# -----------------------------
st.header("7. Финансовый результат")
revenue = menu["Выручка"].sum()
variable_costs = menu["Переменные расходы"].sum()
fixed_costs = (
    rent + electricity + water + gas
    + other_utilities + other_expenses + salary_total
)
profit = revenue - variable_costs - fixed_costs
total_units = menu["Количество продаж"].sum()
margin = revenue - variable_costs
average_margin = margin / total_units if total_units > 0 else 0
break_even = fixed_costs / average_margin if average_margin > 0 else 0

c1, c2, c3 = st.columns(3)
c1.metric("Выручка", f"{revenue:,.2f} грн")
c2.metric("Переменные расходы", f"{variable_costs:,.2f} грн")
c3.metric("Постоянные расходы", f"{fixed_costs:,.2f} грн")

if profit > 0:
    st.success(f"ЧИСТАЯ ПРИБЫЛЬ: {profit:,.2f} грн")
elif profit < 0:
    st.error(f"УБЫТОК: {profit:,.2f} грн")
else:
    st.warning("РАБОТА В НОЛЬ")

c1, c2, c3 = st.columns(3)
c1.metric("Продано порций", f"{total_units:,.0f} шт.")
c2.metric("Прибыль с продаж до постоянных расходов", f"{margin:,.2f} грн")
c3.metric(
    "Рентабельность",
    f"{profit / revenue * 100:.2f}%" if revenue else "0%",
)

st.subheader("Точка безубыточности")
st.metric("Нужно продать единиц меню", f"{break_even:,.0f} шт.")

st.subheader("Экономика каждой позиции")
display_columns = [
    "Название",
    "Продукты",
    "Расходники",
    "Себестоимость",
    "Применённая наценка (%)",
    "Цена продажи",
    "Прибыль с единицы",
    "Количество продаж",
    "Выручка",
    "Переменные расходы",
    "Валовая прибыль",
]
st.dataframe(
    menu[display_columns].style.format(
        {
            "Продукты": "{:,.2f}",
            "Расходники": "{:,.2f}",
            "Себестоимость": "{:,.2f}",
            "Применённая наценка (%)": "{:,.1f}%",
            "Цена продажи": "{:,.2f}",
            "Прибыль с единицы": "{:,.2f}",
            "Выручка": "{:,.2f}",
            "Переменные расходы": "{:,.2f}",
            "Валовая прибыль": "{:,.2f}",
        }
    ),
    use_container_width=True,
)

st.subheader("Расходы предприятия")
expenses_report = pd.DataFrame(
    {
        "Статья": [
            "Аренда",
            "Электричество",
            "Вода",
            "Газ",
            "Другие коммунальные",
            "Прочие расходы",
            "Зарплаты",
            "Продукты и расходники",
        ],
        "Сумма (грн)": [
            rent,
            electricity,
            water,
            gas,
            other_utilities,
            other_expenses,
            salary_total,
            variable_costs,
        ],
    }
)
st.dataframe(expenses_report, use_container_width=True)


