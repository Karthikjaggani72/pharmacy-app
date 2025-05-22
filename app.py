from flask import Flask, render_template, request, redirect, jsonify
import oracledb, pandas as pd, io, datetime
from datetime import datetime
import oracledb
#import cx_Oracle
import datetime

# ---------- Oracle connection ----------
#oracledb.init_oracle_client(lib_dir=r"C:\oracle\instantclient\instantclient_23_8")   # change if needed
def get_db():
    return oracledb.connect(
        user="system",  # <- lowercase is OK
        password="K@j@p0987",
        dsn="localhost/XEPDB1",  # Must match what you used in SQL Developer
        thin=True
    )

# ---------- NEW  START :  daily Day_Bill_ID helpers ----------
def get_today_day_bill_id(conn):
    cur = conn.cursor()
    cur.execute("SELECT NVL(MAX(day_bill_id),0)+1 FROM pharmacy_header WHERE TRUNC(sale_date)=TRUNC(SYSDATE)")
    val = cur.fetchone()[0]
    cur.close()
    return val

def get_next_bill_no(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(bill_no) FROM pharmacy_header")
    last = cur.fetchone()[0]
    cur.close()
    if last:
        next_seq = int(last[1:]) + 1          # strip “B”
    else:
        next_seq = 1
    return f"B{next_seq:06d}"                 # B000001 …

def get_next_day_bill(conn, sale_date):
    cur = conn.cursor()
    cur.execute("SELECT NVL(MAX(day_bill_id),0)+1 FROM pharmacy_header WHERE TRUNC(sale_date)=TRUNC(TO_DATE(:1,'YYYY-MM-DD'))", (sale_date,))
    val = cur.fetchone()[0]
    cur.close()
    return val

app = Flask(__name__)

@app.context_processor
def inject_ids():
    conn = get_db()
    ctx  = {
        "day_bill_id": get_today_day_bill_id(conn),
        "bill_no":     get_next_bill_no(conn)
    }
    conn.close()
    return ctx
# ---------- NEW  END -----------------------------------------

# ---------- Login & dashboard (as before) ----------
# … keep your working login() & dashboard() routes …
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"Received login: {username} / {password}")

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM login WHERE username = :1 AND password = :2", (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                print("✅ Login successful. Redirecting to dashboard.")
                return redirect('/dashboard')
            else:
                print("❌ Login failed. No match found.")
                error = 'Invalid credentials'
        except Exception as e:
            error = f"🔥 Oracle DB Error: {e}"
            print(error)

    return render_template('index.html', error=error)


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# ---------- Master form screen ----------
@app.route('/master')
def master_form():
    return render_template('master_form.html')           # grid UI

# ---------- SAVE  (multiple rows) ----------
@app.route('/master/save', methods=['POST'])
def master_save():
    try:
        rows = zip(
            request.form.getlist('item_name'),
            request.form.getlist('batch_no'),
            request.form.getlist('expiry_date'),
            request.form.getlist('pack'),
            request.form.getlist('available_qty'),
            request.form.getlist('buying_price'),
            request.form.getlist('mrp'),
            request.form.getlist('selling_price')
        )
        conn = get_db(); cur = conn.cursor()
        insert_count = 0
        for r in rows:
            if all(r):
                try:
                    cur.execute("""
                        INSERT INTO master (item_name, batch_no, expiry_date, pack,
                                            available_qty, buying_price, mrp, selling_price)
                        VALUES (:1, :2, TO_DATE(:3, 'YYYY-MM-DD'), :4, :5, :6, :7, :8)
                    """, r)
                    insert_count += 1
                except oracledb.IntegrityError as ie:
                    return f"❌ Duplicate entry for {r[0]} / {r[1]}", 400
                except Exception as ex:
                    return f"❌ DB Error: {ex}", 500
        conn.commit(); cur.close(); conn.close()
        return f"✅ {insert_count} item(s) saved successfully."
    except Exception as e:
        return f"❌ Save Error: {e}", 500


# ---------- SEARCH (simple) ----------
@app.route('/master/search')
def master_search():
    q = request.args.get('q','').upper()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT item_id,item_name,batch_no,expiry_date,pack,
                          available_qty,buying_price,mrp,selling_price
                   FROM master
                   WHERE UPPER(item_name) LIKE :1""", (q + '%',))
    rows = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur]
    cur.close(); conn.close()
    return jsonify(rows)

# ---------- UPLOAD EXCEL ----------
@app.route('/master/upload', methods=['POST'])
def master_upload():
    try:
        file = request.files['excel_file']
        df = pd.read_excel(file)                         # expects same column names
        conn = get_db(); cur = conn.cursor()
        for _, row in df.iterrows():
            cur.execute("""
             INSERT INTO master
               (item_name,batch_no,expiry_date,pack,
                available_qty,buying_price,mrp,selling_price)
             VALUES (:1,:2,TO_DATE(:3,'YYYY-MM-DD'),:4,:5,:6,:7,:8)
            """,
            ( row.item_name, row.batch_no,
              row.expiry_date.strftime('%Y-%m-%d'),
              row.pack, int(row.available_qty),
              float(row.buying_price), float(row.mrp),
              float(row.selling_price) ))
        conn.commit()
        cur.close(); conn.close()
        return "Excel uploaded!"
    except Exception as e:
        return f"Upload error: {e}", 500

@app.route('/pharmacy')
def pharmacy_form():
    return render_template("transaction_form.html", datetime=datetime.datetime)
# -------- SEARCH ITEMS ----------
@app.route('/pharmacy/search_items')
def search_items():
    q = request.args.get('q','').upper()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT item_name, batch_no,
               TO_CHAR(expiry_date,'YYYY-MM-DD') expiry_date,
               pack, available_qty, mrp, selling_price
        FROM master
        WHERE UPPER(item_name) LIKE :1
        FETCH FIRST 20 ROWS ONLY
    """, (q+'%',))
    rows=[dict(zip([d[0].lower() for d in cur.description], r)) for r in cur]
    cur.close(); conn.close()
    return jsonify(rows)

@app.route('/pharmacy/search_bills')
def search_bills():
    q = request.args.get('q', '')
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT bill_no,day_bill_id, TO_CHAR(sale_date,'YYYY-MM-DD') sale_date, customer_name
        FROM pharmacy_header
        WHERE customer_name LIKE :1 OR TO_CHAR(sale_date,'YYYY-MM-DD') LIKE :1
        ORDER BY sale_date DESC
        FETCH FIRST 20 ROWS ONLY
    """, (q+'%',))
    rows = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur]
    cur.close(); conn.close()
    return jsonify(rows)

@app.route('/pharmacy/get_bill')
def get_bill():
    bill_no = request.args.get('bill_no')
    conn = get_db(); cur = conn.cursor()

    # Header
    cur.execute("""SELECT day_bill_id, bill_no,TO_CHAR(sale_date,'YYYY-MM-DD') sale_date, customer_name,
                          doctor_name, prescription_ref, payment_type,
                          total_price, discount_percent, net_total, remarks
                   FROM pharmacy_header WHERE bill_no = :1""", (bill_no,))
    hdr = dict(zip([d[0].lower() for d in cur.description], cur.fetchone()))

    # Items
    cur.execute("""SELECT item_name, batch_no, TO_CHAR(expiry_date,'YYYY-MM-DD') expiry_date,
                          pack, available_qty, mrp, net_price, required_qty, price,
                          new_avl_qty
                   FROM pharmacy_items WHERE bill_no = :1""", (bill_no,))
    items = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur]

    cur.close(); conn.close()
    return jsonify({'header': hdr, 'items': items})

@app.route('/pharmacy/print_bill')
def print_bill():
    bill_no = request.args.get('bill_no')
    print(bill_no)
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM pharmacy_header WHERE bill_no = :1", [bill_no])
    row = cursor.fetchone()
    header = {
        "bill_no": row[0],
        "sale_date": row[1],
        "customer_name": row[2],
        "doctor_name": row[3],
        "payment_type": row[5],
        "total_price": row[6],
        "discount_percent": row[7],
        "net_total": row[8],
        "remarks": row[9]
    }

    cursor.execute("SELECT * FROM pharmacy_items WHERE bill_no = :1", [bill_no])
    items = []
    for row in cursor.fetchall():
        items.append({
            "item_name": row[1],
            "batch_no": row[2],
            "expiry_date": row[3],
            "pack": row[4],
            "required_qty": row[5],
            "net_price": row[6],
            "price": row[7]
        })

    return render_template("print_receipt.html", hdr=header, items=items)




@app.route('/save_pharmacy_item', methods=['POST'])
def save_pharmacy_item():
    try:
        connection = get_db()
        cursor = connection.cursor()

        # Example: assuming multiple rows are submitted
        item_ids = request.form.getlist('item_id')
        required_qtys = request.form.getlist('required_qty')

        for i in range(len(item_ids)):
            item_id = item_ids[i]
            required_qty = int(required_qtys[i])

            # ✅ Step 1: Get available qty from master
            cursor.execute("SELECT qty FROM master WHERE item_id = :item_id", {'item_id': item_id})
            result = cursor.fetchone()
            if not result:
                return f"❌ Item with ID {item_id} not found in master", 400

            available_qty = result[0]

            # ✅ Step 2: Validate quantity
            if required_qty < 1:
                return f"❌ Quantity must be at least 1 for item {item_id}", 400

            if required_qty > available_qty:
                return f"❌ Entered quantity exceeds available stock for item {item_id}", 400

            # ✅ Step 3: Insert into pharmacy_items
            cursor.execute("""
                INSERT INTO pharmacy_items (item_id, qty)
                VALUES (:item_id, :qty)
            """, {'item_id': item_id, 'qty': required_qty})

            # ✅ Step 4: Reduce qty in master
            cursor.execute("""
                UPDATE master SET qty = qty - :qty WHERE item_id = :item_id
            """, {'qty': required_qty, 'item_id': item_id})

        connection.commit()
        cursor.close()
        connection.close()

        return "✅ Pharmacy items saved successfully"

    except Exception as e:
        return f"❌ Error: {str(e)}", 500

@app.route('/pharmacy/reports', methods=['GET', 'POST'])
def pharmacy_reports():
    conn = get_db()
    cur = conn.cursor()

    report_type = request.form.get('report_type', 'daily')

    today = datetime.date.today()
    if report_type == 'daily':
        from_date = to_date = today
    elif report_type == 'weekly':
        from_date = today - datetime.timedelta(days=7)
        to_date = today
    elif report_type == 'monthly':
        from_date = today.replace(day=1)
        to_date = today
    elif report_type == 'quarterly':
        from_date = today - datetime.timedelta(days=90)
        to_date = today

    cur.execute("""
        SELECT day_bill_id, to_char(sale_date), customer_name, net_total
        FROM pharmacy_header
        WHERE Sale_date BETWEEN :from_date AND :to_date
        ORDER BY Sale_date DESC
    """, {"from_date": from_date, "to_date": to_date})

    rows = cur.fetchall()
    total_billing = sum(row[3] for row in rows)

    return render_template('pharmacy_reports.html',
                           report_data=rows,
                           total_billing=total_billing,
                           report_type=report_type)


# -------- SAVE TRANSACTION ----------
@app.route('/pharmacy/save', methods=['POST'])
def save_pharmacy():
    try:
        f    = request.form
        conn = get_db(); cur = conn.cursor()
        bill_no = f['bill_no']  # From hidden input
        print("[DEBUG] Saving bill_no:", bill_no)

        # Duplicate check
        cur.execute("""
            SELECT COUNT(*) FROM pharmacy_header
            WHERE customer_name   = :1
              AND sale_date       = TO_DATE(:2,'YYYY-MM-DD')
              AND prescription_ref = :3
        """, (f['customer_name'], f['sale_date'], f['prescription_ref']))
        if cur.fetchone()[0] > 0:
            return f"Duplicate bill for {f['customer_name']} on {f['sale_date']}"

        # Insert header
        try:
            cur.execute("""
                INSERT INTO pharmacy_header (
                    bill_no, sale_date, customer_name, doctor_name, prescription_ref,
                    payment_type, total_price, discount_percent, net_total, remarks
                ) VALUES (
                    :bill_no, TO_DATE(:sale_date,'YYYY-MM-DD'), :customer_name,
                    :doctor_name, :prescription_ref, :payment_type,
                    :total_price, :discount_percent, :net_total, :remarks
                )
            """, {
                "bill_no": bill_no,
                "sale_date": f['sale_date'],
                "customer_name": f['customer_name'],
                "doctor_name": f['doctor_name'],
                "prescription_ref": f['prescription_ref'],
                "payment_type": f['payment_type'],
                "total_price": f['total_price'],
                "discount_percent": f['discount_percent'],
                "net_total": f['net_total'],
                "remarks": f['remarks']
            })
            print("[DEBUG] Header insert done.")
        except Exception as e:
            print(f"[ERROR] Header insert failed: {e}")
            return f"❌ Save failed: Header insert failed for bill_no {bill_no}", 500

        # Confirm header is inserted
        cur.execute("SELECT bill_no FROM pharmacy_header WHERE bill_no = :1", (bill_no,))
        if not cur.fetchone():
            print("[ERROR] Header not found after insert.")
            return f"❌ Save failed: Header not saved for bill_no {bill_no}", 500

        # Set Day-bill-ID
        next_day_bill = get_next_day_bill(conn, f['sale_date'])
        cur.execute("""
            UPDATE pharmacy_header
            SET    day_bill_id = :1
            WHERE  bill_no     = :2
        """, (next_day_bill, bill_no))
        print("[DEBUG] Day bill ID updated:", next_day_bill)

        # Insert item rows
        rows = zip(
            f.getlist('item_name'), f.getlist('batch_no'), f.getlist('expiry_date'),
            f.getlist('pack'), f.getlist('available_qty'), f.getlist('mrp'),
            f.getlist('net_price'), f.getlist('required_qty'), f.getlist('price'),
            f.getlist('new_avl_qty')
        )
        inserted_items = 0
        for r in rows:
            if all(r) and int(r[7]) > 0:
                cur.execute("""
                    INSERT INTO pharmacy_items
                      (bill_no,item_name,batch_no,expiry_date,pack,available_qty,
                       mrp,net_price,required_qty,price,new_avl_qty)
                    VALUES
                      (:1,:2,:3,TO_DATE(:4,'YYYY-MM-DD'),:5,:6,:7,:8,:9,:10,:11)
                """, (bill_no, *r))
                cur.execute("""
                    UPDATE master
                    SET    available_qty = :1
                    WHERE  item_name     = :2
                      AND  batch_no      = :3
                """, (r[9], r[0], r[1]))
                inserted_items += 1

        conn.commit()
        print(f"[DEBUG] Insert complete: {inserted_items} items for bill {bill_no}")
        return f"✅ Bill {bill_no} saved!"
    except Exception as e:
        print("[ERROR] Save failed:", e)
        return f"❌ Save failed: {e}", 500
    finally:
        try:
            cur.close(); conn.close()
        except:
            pass



if __name__ == '__main__':
    app.run(debug=True)
