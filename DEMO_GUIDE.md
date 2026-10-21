# Company X — Slow Stock Action Tool
## Executive Demonstration & Presentation Guide (5–10 Minutes)

---

### Presentation Overview & Timing

| Time | Step | Objective | Primary Screen / Tab |
| :---: | :--- | :--- | :--- |
| **0:00 – 0:45** | **1. Upload Workbook** | Demonstrate seamless dual ingestion and instant validation | Left Sidebar & Ingestion Checklist |
| **0:45 – 1:30** | **2. Show Data Quality** | Highlight enterprise data governance, deduplication & lineage | **Tab 5**: Data Quality & **Tab 4**: Lineage |
| **1:30 – 2:30** | **3. Executive KPIs** | Present benchmark metrics and the ₹163,841 aged capital opportunity | **Tab 1**: Executive Action Center |
| **2:30 – 3:15** | **4. Explain Push Rules** | Walk through the deterministic R1 $\rightarrow$ R2 $\rightarrow$ R5 decision waterfall | **Tab 1**: Classification Matrix |
| **3:15 – 4:00** | **5. Open a Push SKU** | Inspect slow-moving inventory depth on benchmark SKU1005 | **Tab 2**: Item Analysis / **Tab 3**: Selector |
| **4:00 – 4:45** | **6. Show "Why Push?"** | Demonstrate 100% mathematical explainability for stakeholders | **Tab 3**: Explainability Panel |
| **4:45 – 5:15** | **7. Show Risk Score** | Review the 0–100 Multi-Factor Inventory Obsolescence Index | **Tab 3**: Risk Assessment Card |
| **5:15 – 6:00** | **8. Working Capital Impact** | Present capital-at-risk, category breakdown, and cash recovery | **Tab 1**: Working Capital Module |
| **6:00 – 6:45** | **9. Show Customer Targets** | Review Buckets 1, 2, 3 targeting for SKU1005 (Customers 220, 224, 214) | **Tab 3**: Account Recommendations |
| **6:45 – 7:30** | **10. Sales Action Center** | Showcase dispatch ledger, 7 filters, and live Sales Outreach Tracker | **Tab 3**: Dispatch Matrix & Tracker |
| **7:30 – 8:15** | **11. What-If Simulator** | Model 10%, 25%, 50% sales uplift on clearance time non-destructively | **Tab 2**: What-If Scenario Simulator |
| **8:15 – 9:00** | **12. Export Excel** | Showcase the publication-ready, 12-sheet executive Excel workbook | **Tab 7**: Export Center |

---

### Pre-Presentation Checklist
1. Ensure the Streamlit application is running:
   ```bash
   streamlit run app.py
   ```
2. Open your browser to `http://localhost:8501`.
3. Confirm `sample_data/CompanyX_Data.xlsx` is available on your local machine.
4. Have the application loaded in full-screen mode with the sidebar visible.

---

## Detailed Step-by-Step Script

### Step 1: Upload Workbook (0:00 – 0:45)
**Action**:
1. In the left sidebar, show the **Monthly Data Review** upload card.
2. Ensure **"Combined Workbook"** is selected.
3. Click **Browse Files** and select `CompanyX_Data.xlsx` (or note that the official sample dataset is already pre-loaded).
4. Click the primary button: **"Run Review"**.

**Presenter Script**:
> *"Good morning/afternoon. Today I'm presenting the Company X Slow Stock Action Tool, designed to solve a critical supply-chain challenge: liberating trapped working capital from aged inventory.*
>
> *We begin in the sidebar where inventory managers ingest monthly ERP exports. The tool supports both combined multi-sheet workbooks and separate departmental files. When we run the review, our engine ingests all 42 master items, 42 stock aging records, 630 sales lines, and 30 customer profiles in under one second."*

---

### Step 2: Show Data Quality & Governance (0:45 – 1:30)
**Action**:
1. Click on **Tab 5 (Data Quality)**.
2. Point out the **Master Audit Register** and the **11-step pipeline audit summary**.
3. Point out specific data issues detected:
   - **6 duplicate sales rows** detected and automatically purged.
   - **3 pack-size switch pairs** mapped (`SKU1003 $\rightarrow$ SKU1006`, `SKU1015 $\rightarrow$ SKU1019`, `SKU1030 $\rightarrow$ SKU1033`).
   - **1 inactive catalog item holding warehouse stock** (`SKU1041`, 169 units, ₹14,365) isolated from active sales push.
   - **Customers with missing Industry** flagged to prevent unauthorized Bucket 2 entry.
4. Briefly switch to **Tab 4 (Data Lineage / Audit)** to show the visual 12-stage pipeline flow.

**Presenter Script**:
> *"Before calculating a single rupee of inventory value, the tool subjects the dataset to a rigorous 13-point data governance check. Unlike black-box tools that silently discard records, Company X enforces full transparency.*
>
> *Here in Tab 5, the tool detected 6 duplicate sales transactions and purged them before velocity calculations. It mapped 3 superseded pack-sizes under Rule R3, and under Rule R4, it isolated SKU1041—an inactive item still holding ₹14,365 in physical warehouse stock. In Tab 4, our 12-stage lineage flow provides an auditable paper trail from raw input to the final sales call list."*

---

### Step 3: Show Executive KPIs & Benchmark Checks (1:30 – 2:30)
**Action**:
1. Click on **Tab 1 (Executive Action Center)**.
2. Highlight the 4 primary KPI cards at the top:
   - **Red List Items**: `7`
   - **No Action Items**: `13`
   - **Push Items**: `18`
   - **Push Aged Value**: `₹163,841`
3. Scroll down slightly to show the green **Verified Case Regression Benchmarks** container.

**Presenter Script**:
> *"Now let's examine the Executive Action Center in Tab 1. Our deterministic engine has classified the entire 38 active catalog items into three clear tiers:*
>
> *- **7 Red List items**: severe stagnation requiring supplier return or scrap write-off.*
> *- **13 No Action items**: healthy turnover clearing in under 3 months.*
> *- **18 Push items**: actionable slow-movers requiring proactive commercial liquidation.*
>
> *Crucially, these 18 Push items represent **₹163,841** in tied-up aged working capital. As you can see in our Case Benchmark Verification card, these figures match the official MBA case benchmarks to the exact single rupee."*

---

### Step 4: Explain Push Classification (2:30 – 3:15)
**Action**:
1. Point to the **Sequential Classification Hierarchy (Rule R5)** diagram in Tab 1.
2. Explain the strict sequential waterfall:
   - Check 1: 6-Month Sales < 1 Master Pack? $\rightarrow$ **Red List**.
   - Check 2: Months to Clear < 3.0 months? $\rightarrow$ **No Action**.
   - Check 3: Slow-moving with Aged Stock > 0? $\rightarrow$ **Push**.

**Presenter Script**:
> *"How did the tool arrive at these classifications? It follows the strict sequential hierarchy of Rule R5:*
>
> *First, it tests demand viability: if an item cannot sell even one wholesale master pack over six months, it immediately goes to the Red List under Rule R1.*
>
> *Second, if demand is viable, it checks clearance velocity: if total stock clears in under 3.0 months, it is classified as No Action under Rule R2—it's turning normally.*
>
> *Third, items with more than 3 months of supply and aged inventory older than 90 days are classified as Push. This prevents subjectivity and ensures sales reps focus only on genuine capital blockages."*

---

### Step 5: Open a Push SKU (3:15 – 4:00)
**Action**:
1. Navigate to **Tab 3 (Sales Action Center)**.
2. In the **Push SKU Selector** dropdown, select:
   `Rank #... SKU1005 — C-Product 05 (100/case)`.
3. Review the top metrics card:
   - **Category**: Category C
   - **Unit Cost**: ₹155
   - **Aged Value**: ₹5,115 (33 aged units)
   - **Months to Clear**: 5.68 months (or 8.01 months on total stock)
   - **Sales Trend**: Growing (+38.1% MoM)

**Presenter Script**:
> *"Let's move into Tab 3—the commercial execution heart of the platform. Here, sales managers select any Push item to inspect. Let's look at **SKU1005**.*
>
> *SKU1005 has 33 aged units valued at ₹5,115. Its runway velocity indicates over 5.6 months to clear, which means it is tying up capital and taking up warehouse pallet space. Notice also that our sales trend engine recognizes this SKU has +38.1% month-over-month growth—so customer momentum exists if we direct sales reps to the right buyers."*

---

### Step 6: Show "Why Push?" (Explainability Panel) (4:00 – 4:45)
**Action**:
1. Expand the accordion: **"🔍 WHY THIS ITEM IS CLASSIFIED THIS WAY (Explainability Panel)"**.
2. Walk through the three mathematical steps displayed:
   - **Rule R1 Check**: 6M Sales (280) $\ge$ Master Pack (100) $\rightarrow$ Passed (Not Red List).
   - **Rule R2 Check**: Months to Clear (5.68 m) $\ge$ 3.0 m $\rightarrow$ Fails No Action threshold.
   - **Rule R5 Check**: Aged Qty (33 units) > 0 $\rightarrow$ Qualifies as Push!

**Presenter Script**:
> *"A key differentiator of this tool is 100% mathematical explainability. When a sales rep or category manager asks: 'Why is SKU1005 on the Push list?', we open the Explainability Panel.*
>
> *The system demonstrates step-by-step:*
> *1. 6-month sales were 280 units, clearing the 100-unit master pack hurdle—so it is not dead stock.*
> *2. Total inventory runway exceeds the 3.0-month threshold—so it is not fast-moving.*
> *3. It holds 33 aged units past 90 days.*
> *Therefore, it deterministically qualifies as Push. No guesswork, no disputes."*

---

### Step 7: Show Risk Score (4:45 – 5:15)
**Action**:
1. Point to the **Risk Assessment Card** next to SKU1005:
   `Risk Score: 45 / 100 (Medium Risk)`.
2. Read the **Risk Driver Insight**:
   *"Moderate inventory risk: 33 aged units (₹5,115) with 5.7 months to clear, balanced by positive sales momentum (+38.1% MoM)."*

**Presenter Script**:
> *"Alongside classification, every SKU receives an objective **0–100 Inventory Risk Score**. This multi-factor score evaluates aged stock concentration, runway months, sales velocity trend, demand relative to pack size, and absolute capital exposure.*
>
> *SKU1005 receives a score of 45/100—Medium Risk. It has aged units, but its risk is mitigated by strong recent sales. This prevents sales teams from panicking and offering unnecessary discounts on recoverable stock."*

---

### Step 8: Show Working Capital Impact (5:15 – 6:00)
**Action**:
1. Switch back to **Tab 1 (Executive Action Center)**.
2. Scroll to the **Working Capital Impact & Liquidation Target Module**.
3. Show the financial metrics:
   - **Total Active Inventory Value** vs **Total Aged Capital**
   - **Push Aged Capital**: Exactly **₹163,841**
   - **Category Breakdown Chart**: Aged capital distribution across Categories A, B, C, and D.
   - **Top 10 Aged SKUs Table**.

**Presenter Script**:
> *"From an executive CFO perspective, Tab 1 translates inventory units into cash flow. Across our 18 Push items, Company X has **₹163,841 in aged inventory** older than 90 days.*
>
> *Our Category Breakdown reveals that Category B and Category C carry the highest aged inventory exposure. By executing targeted sales pushes rather than writing off stock, the company can recover up to ₹163,841 in immediate operating liquidity."*

---

### Step 9: Show Customer Targets (Buckets 1, 2, 3) (6:00 – 6:45)
**Action**:
1. Return to **Tab 3 (Sales Action Center)** with `SKU1005` selected.
2. Show the **Targeted Account Recommendations** table:
   - **Rank #1: Customer 220** &bull; Bucket 1 (Bought Before) &bull; Spend: ₹665,004
   - **Rank #2: Customer 224** &bull; Bucket 1 (Bought Before) &bull; Spend: ₹1,003,130
   - **Rank #3: Customer 214** &bull; Bucket 2 (Similar Industry: Caterer) &bull; Spend: ₹259,576
3. Show the **Relevant Purchase Evidence** column.
4. Toggle between **Desktop Table** and **Mobile Action Cards** to show the responsive layout.

**Presenter Script**:
> *"Now we answer the primary field question: **Who should the salesperson call today, and what should they sell?***
>
> *Under Rules R6 and R7, we filter exclusively for commercial accounts with over ₹100,000 in 6-month spend, waterfalling them across three mutually exclusive affinity buckets:*
>
> *- **Bucket 1 (Repeat Buyers)**: Customer 220 and Customer 224 previously bought SKU1005 and have massive spend. They are our highest-probability buyers.*
> *- **Bucket 2 (Similar Industry)**: Customer 214 is a Caterer who hasn't bought SKU1005, but operates in the exact same industry as previous buyers.*
>
> *Notice our mutual exclusivity: Customer 220 appears strictly in Bucket 1 and is never duplicated into Buckets 2 or 3. And for sales reps on their phones, clicking 'Mobile Action Cards' switches to a thumb-friendly card layout."*

---

### Step 10: Show Sales Action Center & Sales Tracker (6:45 – 7:30)
**Action**:
1. Scroll up to the **Dedicated Sales Action Center & Consolidated Cross-Portfolio Calling Ledger**.
2. Demonstrate filtering:
   - Select `Bucket 1 (Bought Before)` in the **Filter Customer Bucket** dropdown.
   - Show how the table instantly filters to high-conversion repeat accounts.
3. Reset filter and scroll down to the **Commercial Outreach & Sales Execution Tracker**:
   - Open the **"Log / Update Call Disposition"** form.
   - Select a lead, set status to `Order Placed (Liquidated)`, enter `25` units and `₹50,000` value, and click **Save Call Log Entry**.
   - Show the live KPI cards updating: Total Leads, Contacted, Orders Placed, and Capital Liquidated.

**Presenter Script**:
> *"At the top of Tab 3, sales leadership has a single cross-portfolio ledger combining all 18 Push SKUs and their customer opportunities. With 7 multi-parameter filters, reps can filter by Industry, Priority tier, or specific Customer ID.*
>
> *Furthermore, our **Sales Outreach & Execution Tracker** enables reps to log call outcomes directly in the tool. When a rep logs an order, the system immediately tracks committed units, realized revenue, and updates the team's conversion rate in real time."*

---

### Step 11: Demonstrate What-If Scenario Simulator (7:30 – 8:15)
**Action**:
1. Navigate to **Tab 2 (Item Analysis)**.
2. Select `SKU1005` in the SKU detail view and scroll to the **What-If Scenario Simulator**.
3. Select the **25% sales uplift** radio button (or enter a custom uplift).
4. Review the simulated outputs:
   - **Current vs Simulated Avg Monthly Sales**: `46.7 units $\rightarrow$ 58.3 units`
   - **Current vs Simulated Months to Clear**: `5.68 months $\rightarrow$ 4.54 months`
   - **Stock Clearance Acceleration**: Clears `1.14 months faster`
5. Emphasize that source data and R1–R7 classifications remain completely uncorrupted.

**Presenter Script**:
> *"In Tab 2, inventory controllers can model scenarios before launching sales incentives. Using our What-If Simulator, we can test a 25% sales uplift on SKU1005.*
>
> *The model instantly shows that a 25% uplift accelerates monthly sales from 46.7 to 58.3 units, shortening the clearance horizon from 5.7 months down to 4.5 months. Crucially, this simulation is non-destructive and 100% reversible—it does not alter the underlying dataset or the official R1–R7 classifications."*

---

### Step 12: Export Excel (8:15 – 9:00)
**Action**:
1. Click on **Tab 7 (Export)**.
2. Show the list of 12 distinct worksheets included in the executive report.
3. Click the primary button: **"📥 Download Complete Excel Report (.xlsx)"**.
4. Mention the included **Assumptions & Rules** sheet documenting Rules R1–R7.

**Presenter Script**:
> *"Finally, in Tab 7, we provide complete offline reporting. With one click, the tool exports a publication-grade, 12-sheet Excel workbook.*
>
> *This includes Executive Summaries, SKU Analysis, Push Lists, Red Lists, Customer Targets, Risk Rankings, Working Capital, Dead Stock, Data Quality registers, and a dedicated Assumptions & Rules worksheet documenting Rules R1 through R7.*
>
> *Every sheet features corporate navy headers, frozen panes, autofilters, and proper currency and percentage formatting, ready for executive board presentation.*
>
> *Thank you. I welcome any questions."*

---

## Executive Q&A Defense Talking Points

### Q1: "Why don't we just discount all aged stock to get rid of it?"
> *"Indiscriminate discounting destroys gross margin and trains customers to delay purchases. Our tool uses Rules R6 and R7 to target customers who already value the product (Bucket 1) or operating in peer industries (Bucket 2). By approaching qualified buyers with targeted needs, sales reps can liquidate stock at full or near-full price without brand erosion."*

### Q2: "Can the AI hallucinate prices or change inventory metrics?"
> *"Absolutely not. The architecture enforces a strict boundary: AI is strictly barred from computing financial metrics, classifying SKUs, or determining customer buckets. All calculations are 100% deterministic Python/Pandas logic. The optional AI layer is restricted exclusively to commercial phrasing for WhatsApp and emails, with programmatic sanitizers preventing it from inventing prices, discounts, or delivery dates."*

### Q3: "What happens if a customer has missing industry data?"
> *"Under Rule R7, missing data is handled conservatively: an account with missing Industry is barred from entering Bucket 2 affinity targeting. However, they remain eligible for Bucket 1 if they previously bought the SKU, or Bucket 3 if they bought from the category. All missing industry accounts are flagged in Tab 5 for master data remediation."*

### Q4: "How does the tool handle superseded pack-sizes (SWITCH)?"
> *"Under Rule R3, when an item has `Alternate Flag == 'SWITCH'`, historical sales and warehouse stock are automatically credited to the new replacement SKU. The old superseded SKU is retired from analytical reporting. This ensures sales reps only sell active, orderable pack-sizes."*

---
*Authored for the Company X Slow Stock Action Tool Executive Defense.*
