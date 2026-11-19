# -*- coding: utf-8 -*-
"""모멘텀 상세 읽기 전용 뷰 서버

메인 API(main.py, 8000번 포트)와 완전히 분리된 최소 서버.
포트포워딩으로 외부에 노출해도 조회(GET) 외에는 아무 것도 할 수 없어
포트폴리오 변경/작업 실행 같은 위험한 엔드포인트에는 닿지 않는다.
"""

import hmac
import hashlib
import logging
import time
from datetime import date, datetime, timezone
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from config import PENSION_ETFS, IRP_PORTFOLIO, LOG_LEVEL, PORTFOLIO_EDIT_PIN, PORTFOLIO_SESSION_SECRET
from database import get_db, ETFPrice, MomentumScore
from portfolio_engine import PortfolioEngine
from performance_report_engine import PerformanceReportEngine, ACCOUNT_TYPES

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ReBalancer Momentum View")

SESSION_COOKIE_NAME = "rb_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30일


def _make_session_token() -> str:
    expiry = str(int(time.time()) + SESSION_MAX_AGE)
    sig = hmac.new(PORTFOLIO_SESSION_SECRET.encode(), expiry.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def _is_valid_session_token(token: str) -> bool:
    try:
        expiry_str, sig = token.split(".", 1)
        if int(expiry_str) < time.time():
            return False
    except (ValueError, AttributeError):
        return False
    expected_sig = hmac.new(PORTFOLIO_SESSION_SECRET.encode(), expiry_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def _has_valid_session(request: Request) -> bool:
    if not PORTFOLIO_SESSION_SECRET:
        return False
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return bool(token) and _is_valid_session_token(token)


def _login_page_html(error: str = "") -> str:
    error_html = f'<p class="error">{error}</p>' if error else ""
    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>로그인</title>
        <style>
            body {{ font-family: sans-serif; padding: 24px; }}
            input {{ font-size: 22px; padding: 10px; width: 180px; letter-spacing: 6px; text-align: center; }}
            button {{ font-size: 16px; padding: 10px 18px; margin-left: 8px; }}
            .error {{ color: #dc2626; }}
            .hint {{ color: #888; font-size: 12px; margin-top: 12px; }}
        </style>
    </head>
    <body>
        <h3>포트폴리오 관리 - PIN 입력</h3>
        {error_html}
        <form method="post" action="/portfolio/login">
            <input type="password" inputmode="numeric" pattern="[0-9]*" maxlength="6" name="pin" autofocus required>
            <button type="submit">확인</button>
        </form>
        <p class="hint">한 번 입력하면 이 브라우저에서 30일간 다시 묻지 않습니다.</p>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/momentum/view", response_class=HTMLResponse)
async def view_latest_momentum(db: Session = Depends(get_db)) -> str:
    latest = db.query(MomentumScore).order_by(MomentumScore.calc_date.desc()).first()
    if not latest:
        return "<html><body><p>모멘텀 데이터가 없습니다</p></body></html>"

    calc_date = latest.calc_date
    scores = db.query(MomentumScore).filter(MomentumScore.calc_date == calc_date).order_by(
        MomentumScore.weighted_score.desc()
    ).all()

    rows_html = ""
    for s in scores:
        name = PENSION_ETFS.get(s.ticker, {}).get("name", s.ticker)
        price_row = db.query(ETFPrice).filter(
            ETFPrice.ticker == s.ticker, ETFPrice.price_date <= calc_date
        ).order_by(ETFPrice.price_date.desc()).first()
        price = f"{price_row.close_price:,.0f}" if price_row else "-"
        ma10 = f"{s.ma10:,.0f}" if s.ma10 else "-"
        pass_mark = "O" if s.passed_condition else "X"
        pass_cls = "up" if s.passed_condition else "down"
        mark = "O" if s.is_selected else ""
        row_class = " class=\"selected\"" if s.is_selected else ""

        def ret_cell(value: float) -> str:
            cls = "up" if value > 0 else "down" if value < 0 else ""
            return f'<td class="{cls}">{value:+.2f}%</td>'

        rows_html += (
            f"<tr{row_class}><td>{name}</td><td>{s.ticker}</td><td>{price}원</td>"
            f"{ret_cell(s.r3)}{ret_cell(s.r6)}{ret_cell(s.r12)}"
            f"<td>{s.weighted_score:.2f}</td><td>{ma10}원</td>"
            f"<td class=\"{pass_cls}\">{pass_mark}</td><td>{mark}</td></tr>"
        )

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>모멘텀 상세 - {calc_date}</title>
        <style>
            body {{ font-family: sans-serif; padding: 16px; }}
            .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
            table {{ border-collapse: collapse; width: 100%; min-width: 560px; font-size: 14px; }}
            th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: right; white-space: nowrap; }}
            th:first-child, td:first-child {{ text-align: left; white-space: normal; }}
            th {{ background: #f4f4f5; }}
            td.up {{ color: #d92626; }}
            td.down {{ color: #2563eb; }}
            tr.selected td {{ font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>모멘텀 상세 ({calc_date})</h2>
        <div class="table-scroll">
        <table>
            <tr><th>종목명</th><th>티커</th><th>현재종가</th><th>3개월</th><th>6개월</th><th>12개월</th><th>스코어</th><th>MA10</th><th>통과</th><th>선정</th></tr>
            {rows_html}
        </table>
        </div>
    </body>
    </html>
    """


_ALL_ETFS = {**PENSION_ETFS, **IRP_PORTFOLIO}


def _account_options_html(selected_account: str) -> str:
    opts = ""
    for value in ("연금저축", "IRP"):
        sel = " selected" if value == selected_account else ""
        opts += f"<option value=\"{value}\"{sel}>{value}</option>"
    return opts


def _render_portfolio_edit_page(
    db: Session,
    message: str = "",
    edit_ticker: str = "",
    edit_account: str = "",
) -> str:
    engine = PortfolioEngine(db)
    performance = engine.calculate_portfolio_performance()

    holdings_by_account = {}
    for h in performance["holdings"]:
        holdings_by_account.setdefault(h.get("account_type", ""), []).append(h)

    edit_holding = None
    tables_html = ""
    for account_type in ("연금저축", "IRP"):
        holdings = holdings_by_account.get(account_type, [])
        if not holdings:
            continue

        total_value = sum(h["current_value"] for h in holdings)

        # 목표비중 설정
        target_weights = {}
        if account_type == "IRP":
            from config import IRP_PORTFOLIO
            for ticker, info in IRP_PORTFOLIO.items():
                target_weights[ticker] = info.get("target_weight", 0)
        else:  # 연금저축
            # Top2 기반 50% 각
            for h in holdings:
                target_weights[h["ticker"]] = 50.0 if h.get("is_selected") else 0.0

        total_cost = sum(h["cost_value"] for h in holdings)
        total_return = total_value - total_cost
        total_return_pct = (total_return / total_cost * 100) if total_cost > 0 else 0
        total_cls = "up" if total_return_pct > 0 else "down" if total_return_pct < 0 else ""

        rows_html = ""
        for h in holdings:
            cls = "up" if h["unrealized_return_pct"] > 0 else "down" if h["unrealized_return_pct"] < 0 else ""
            if edit_ticker and h["ticker"] == edit_ticker and account_type == edit_account:
                edit_holding = h

            weight_pct = (h["current_value"] / total_value * 100) if total_value > 0 else 0.0
            target_pct = target_weights.get(h["ticker"], 0)
            diff = weight_pct - target_pct
            diff_cls = "diff-over" if diff > 0 else "diff-under" if diff < 0 else ""

            # 현금 특별 처리
            if h["ticker"] == "CASH":
                rows_html += (
                    f"<tr><td>{h.get('name', h['ticker'])}</td>"
                    f"<td class=\"weight-cell\"><span>{weight_pct:.1f}%</span>"
                    f"<span class=\"diff {diff_cls}\">({diff:+.1f}%p)</span></td>"
                    f"<td colspan=\"3\"></td>"
                    f"<td>{h['current_value']:,.0f}</td>"
                    f"<td>{h['current_value']:,.0f}</td>"
                    f"<td>-</td>"
                    f"<td>"
                    f"<a href=\"/portfolio/edit?edit_ticker={h['ticker']}&edit_account={quote(account_type)}\">"
                    f"<button type=\"button\">수정</button></a> "
                    f"<form method=\"post\" action=\"/portfolio/edit/delete\" style=\"display:inline\" "
                    f"onsubmit=\"return confirm('삭제하시겠습니까?')\">"
                    f"<input type=\"hidden\" name=\"ticker\" value=\"{h['ticker']}\">"
                    f"<input type=\"hidden\" name=\"account_type\" value=\"{account_type}\">"
                    f"<button type=\"submit\">삭제</button></form></td></tr>"
                )
            else:
                rows_html += (
                    f"<tr><td>{h.get('name', h['ticker'])}</td>"
                    f"<td class=\"weight-cell\"><span>{weight_pct:.1f}%</span>"
                    f"<span class=\"diff {diff_cls}\">({diff:+.1f}%p)</span></td>"
                    f"<td>{h['quantity']:g}</td>"
                    f"<td>{h['avg_buy_price']:,.0f}</td><td>{h['current_price']:,.0f}</td>"
                    f"<td>{h['cost_value']:,.0f}</td>"
                    f"<td>{h['current_value']:,.0f}</td>"
                    f"<td class=\"{cls}\">{h['unrealized_return_pct']:+.2f}%</td>"
                    f"<td>"
                    f"<a href=\"/portfolio/edit?edit_ticker={h['ticker']}&edit_account={quote(account_type)}\">"
                    f"<button type=\"button\">수정</button></a> "
                    f"<form method=\"post\" action=\"/portfolio/edit/delete\" style=\"display:inline\" "
                    f"onsubmit=\"return confirm('삭제하시겠습니까?')\">"
                    f"<input type=\"hidden\" name=\"ticker\" value=\"{h['ticker']}\">"
                    f"<input type=\"hidden\" name=\"account_type\" value=\"{account_type}\">"
                    f"<button type=\"submit\">삭제</button></form></td></tr>"
                )

        rows_html += (
            f'<tr class="total-row"><td>합계</td><td colspan="4"></td>'
            f'<td>{total_cost:,.0f}</td>'
            f'<td>{total_value:,.0f}</td>'
            f'<td class="{total_cls}">{total_return_pct:+.2f}%</td><td></td></tr>'
        )

        tables_html += f"""
        <h3>{account_type}</h3>
        <div class="table-scroll">
        <table>
            <tr><th>종목명</th><th>비중</th><th>수량</th><th>평단가</th><th>현재가</th><th>매입금액</th><th>평가금액</th><th>수익률</th><th></th></tr>
            {rows_html}
        </table>
        </div>
        """

    def ticker_options_html(selected_ticker: str) -> str:
        opts = ""
        for ticker, info in _ALL_ETFS.items():
            sel = " selected" if ticker == selected_ticker else ""
            opts += f"<option value=\"{ticker}\"{sel}>{info['name']} ({ticker})</option>"
        return opts

    form_title = "수정" if edit_holding else "추가 / 수정"
    quantity_value = f' value="{edit_holding["quantity"]:g}"' if edit_holding else ""
    avg_price_value = f' value="{edit_holding["avg_buy_price"]:g}"' if edit_holding else ""
    ticker_select = ticker_options_html(edit_holding["ticker"] if edit_holding else "")
    account_select = _account_options_html(edit_holding.get("account_type", "") if edit_holding else "")

    message_html = f'<p class="msg">{message}</p>' if message else ""

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>포트폴리오 관리</title>
        <style>
            body {{ font-family: sans-serif; padding: 16px; }}
            .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
            table {{ border-collapse: collapse; width: 100%; min-width: 640px; font-size: 14px; }}
            th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: right; white-space: nowrap; }}
            th:first-child, td:first-child {{ text-align: left; white-space: normal; }}
            th {{ background: #f4f4f5; }}
            td.up {{ color: #d92626; }}
            td.down {{ color: #2563eb; }}
            td.weight-cell {{ display: flex; flex-direction: column; align-items: flex-end; }}
            td.weight-cell span {{ display: block; }}
            span.diff {{ font-size: 12px; color: #666; }}
            span.diff.diff-over {{ color: #d92626; }}
            span.diff.diff-under {{ color: #2563eb; }}
            form.add-form {{ margin-top: 20px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
            form.add-form input, form.add-form select {{ padding: 6px; font-size: 14px; }}
            button {{ padding: 6px 12px; font-size: 14px; }}
            .msg {{ color: #16a34a; font-weight: bold; }}
            tr.total-row td {{ font-weight: bold; background: #f4f4f5; text-align: right; }}
            label {{ display: inline-block; width: 80px; font-size: 12px; color: #666; }}
        </style>
        <script>
            function updateFormType() {{
                const ticker = document.querySelector('select[name="ticker"]').value;
                const cashQuantity = document.getElementById('cash-quantity');
                const etfQuantity = document.getElementById('etf-quantity');
                const etfAvgPrice = document.getElementById('etf-avg-price');

                if (ticker === 'CASH') {{
                    cashQuantity.style.display = 'block';
                    cashQuantity.disabled = false;
                    etfQuantity.style.display = 'none';
                    etfQuantity.disabled = true;
                    etfAvgPrice.style.display = 'none';
                    etfAvgPrice.disabled = true;
                }} else {{
                    cashQuantity.style.display = 'none';
                    cashQuantity.disabled = true;
                    etfQuantity.style.display = 'block';
                    etfQuantity.disabled = false;
                    etfAvgPrice.style.display = 'block';
                    etfAvgPrice.disabled = false;
                }}
            }}

            document.addEventListener('DOMContentLoaded', updateFormType);
        </script>
    </head>
    <body>
        <h2>포트폴리오 관리</h2>
        {message_html}
        {tables_html if tables_html else '<p>보유 종목이 없습니다.</p>'}

        <h3>{form_title}</h3>

        <form class="add-form" method="post" action="/portfolio/edit/upsert">
            <select name="ticker" required onchange="updateFormType()">{ticker_select}</select>
            <select name="account_type" required>{account_select}</select>

            <!-- 현금 입력 필드 -->
            <input type="number" step="any" name="quantity" id="cash-quantity" placeholder="금액" style="display:none;" required>
            <input type="hidden" name="avg_buy_price" id="cash-avg-price" value="1">

            <!-- 일반 종목 입력 필드 -->
            <input type="number" step="any" name="quantity" id="etf-quantity" placeholder="수량"{quantity_value} required>
            <input type="number" step="any" name="avg_buy_price" id="etf-avg-price" placeholder="평단가"{avg_price_value} required>

            <button type="submit">저장</button>
            {'<a href="/portfolio/edit"><button type="button">취소</button></a>' if edit_holding else ''}
        </form>

        <p style="color:#888; font-size:12px;">
            현금을 선택하면 금액 입력으로, 종목을 선택하면 수량/평단가 입력으로 전환됩니다.
            <br>같은 종목+계좌 조합이 이미 있으면 값을 덮어씁니다. 표의 "수정" 버튼을 누르면 기존 값이 채워집니다.
        </p>
    </body>
    </html>
    """


@app.get("/portfolio/login", response_class=HTMLResponse)
async def portfolio_login_page(error: str = "") -> str:
    return _login_page_html(error)


@app.post("/portfolio/login")
async def portfolio_login_submit(pin: str = Form(...)):
    if not PORTFOLIO_EDIT_PIN or not hmac.compare_digest(pin, PORTFOLIO_EDIT_PIN):
        return RedirectResponse(
            url=f"/portfolio/login?error={quote('PIN이 올바르지 않습니다')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    response = RedirectResponse(url="/portfolio/edit", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        _make_session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/portfolio/edit", response_class=HTMLResponse)
async def portfolio_edit_page(
    request: Request,
    edit_ticker: str = "",
    edit_account: str = "",
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    return _render_portfolio_edit_page(db, edit_ticker=edit_ticker, edit_account=edit_account)


@app.post("/portfolio/edit/upsert")
async def portfolio_edit_upsert(
    request: Request,
    ticker: str = Form(...),
    account_type: str = Form(...),
    quantity: float = Form(...),
    avg_buy_price: float = Form(...),
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)

    engine = PortfolioEngine(db)
    existing = engine.get_portfolio_by_ticker(ticker, account_type)
    if existing:
        engine.update_portfolio_holding(ticker, quantity, avg_buy_price, account_type)
    else:
        engine.add_portfolio_holding(ticker, quantity, avg_buy_price, account_type)
    return RedirectResponse(url="/portfolio/edit", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/portfolio/edit/delete")
async def portfolio_edit_delete(
    request: Request,
    ticker: str = Form(...),
    account_type: str = Form(...),
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    engine = PortfolioEngine(db)
    engine.delete_portfolio_holding(ticker, account_type)
    return RedirectResponse(url="/portfolio/edit", status_code=status.HTTP_303_SEE_OTHER)


def _pct_cell(value) -> str:
    if value is None:
        return '<td>—</td>'
    cls = "up" if value > 0 else "down" if value < 0 else ""
    return f'<td class="{cls}">{value:+.2f}%</td>'


def _render_asset_trend_chart(default_account: str) -> str:
    """ApexCharts 캔들스틱(주간/월간/연간 스위칭, 계좌 드롭다운)을 렌더링.
    데이터는 /report/ohlc에서 비동기로 가져온다."""
    account_options = "".join(
        f'<option value="{acc}"{" selected" if acc == default_account else ""}>{acc}</option>'
        for acc in ACCOUNT_TYPES
    )
    return f"""
    <div>
        <div style="margin-bottom:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <select id="ohlc-account">{account_options}</select>
            <button type="button" class="period-btn" data-period="weekly">주간</button>
            <button type="button" class="period-btn" data-period="monthly">월간</button>
            <button type="button" class="period-btn" data-period="yearly">연간</button>
        </div>
        <div id="ohlc-chart"></div>
        <p style="color:#888; font-size:12px;">
            단위: 만원. 하루 1회(18시) 스냅샷 기준 근사 캔들입니다(시가=기간 첫 스냅샷, 종가=마지막 스냅샷,
            고가/저가=기간 내 최대/최소, 장중 변동 미반영).
        </p>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/apexcharts@3.54.1/dist/apexcharts.min.js"
            integrity="sha384-KNaFJ+EK516RuHsoycvreec5pD7BkTKJEkjMrVSQWu9KGTl7En4dhIDv7t1DFJ+g"
            crossorigin="anonymous"></script>
    <script>
    (function() {{
        var account = document.getElementById('ohlc-account');
        var period = 'monthly';

        function pad(n) {{ return n < 10 ? '0' + n : '' + n; }}

        function formatTooltipDate(val) {{
            var d = new Date(val);
            var y = d.getUTCFullYear(), m = pad(d.getUTCMonth() + 1), day = pad(d.getUTCDate());
            if (period === 'weekly') return y + '/' + m + '/' + day;
            if (period === 'monthly') return y + '/' + m;
            return '' + y;
        }}

        var chart = new ApexCharts(document.querySelector('#ohlc-chart'), {{
            chart: {{ type: 'candlestick', height: 340 }},
            series: [{{ data: [] }}],
            plotOptions: {{
                candlestick: {{
                    colors: {{ upward: '#d92626', downward: '#2563eb' }},
                    wick: {{ useFillColor: true }}
                }}
            }},
            tooltip: {{ shared: false, intersect: true, x: {{ formatter: formatTooltipDate }} }},
            xaxis: {{ type: 'datetime', crosshairs: {{ width: 'barWidth' }} }},
            yaxis: {{ tooltip: {{ enabled: true }} }}
        }});
        chart.render();

        function reload() {{
            fetch('/report/ohlc?account_type=' + encodeURIComponent(account.value) + '&period=' + period)
                .then(function(res) {{ return res.json(); }})
                .then(function(json) {{ chart.updateSeries([{{ data: json.data }}]); }});
        }}

        document.querySelectorAll('.period-btn').forEach(function(btn) {{
            btn.addEventListener('click', function() {{
                period = btn.dataset.period;
                document.querySelectorAll('.period-btn').forEach(function(b) {{ b.classList.remove('active'); }});
                btn.classList.add('active');
                reload();
            }});
        }});
        account.addEventListener('change', reload);

        document.querySelector('.period-btn[data-period="monthly"]').classList.add('active');
        reload();
    }})();
    </script>
    """


_REVIEW_TARGETS = ACCOUNT_TYPES + ["전체"]


def _render_comprehensive_review_section(engine: PerformanceReportEngine) -> str:
    """계좌별 + 합산 전체 기준 종합 점검 지표(순입금대비수익률/연평균 단순·가중/CAGR/MDD)."""
    cards_html = ""
    for acc in _REVIEW_TARGETS:
        cum_return = engine.get_cumulative_return_vs_deposits(acc)
        annual = engine.get_annual_return_simple_weighted(acc)
        cagr = engine.get_cagr(acc)
        mdd = engine.get_mdd(acc)

        cards_html += f"""
        <h3>{acc}</h3>
        <table class="summary">
            <tr><td>순입금 대비 수익률</td>{_pct_cell(cum_return)}</tr>
            <tr><td>연평균 수익률 (단순)</td>{_pct_cell(annual['simple'])}</tr>
            <tr><td>연평균 수익률 (가중)</td>{_pct_cell(annual['weighted'])}</tr>
            <tr><td>CAGR</td>{_pct_cell(cagr)}</tr>
            <tr><td>MDD</td>{_pct_cell(mdd)}</tr>
        </table>
        """

    return f"""
    <div>
        {cards_html}
        <p style="color:#888; font-size:12px;">
            연평균(가중)은 그 해 평균 자산 규모로 가중치를 준 값입니다. CAGR/MDD/연평균 모두
            입금 효과를 제거한 성장지수 기준이며, 데이터 기간이 짧을수록(현재 스냅샷 축적 초기)
            오차가 커질 수 있습니다. 순입금 대비 수익률은 입금 기록(/deposit)이 없으면 "—"로 표시됩니다.
        </p>
    </div>
    """


def _render_performance_report_page(db: Session, account_type: str, year: int, month: int, mode: str) -> str:
    engine = PerformanceReportEngine(db)
    targets = [account_type] if account_type in ACCOUNT_TYPES else ACCOUNT_TYPES

    sections_html = ""
    for acc in targets:
        if mode == "yearly":
            report = engine.get_yearly_report(acc, year)
            period_label = f"{year}년"
            breakdown_rows = ""
            for m in report["monthly_breakdown"]:
                breakdown_rows += (
                    f"<tr><td>{m['start_date'][:7]}</td>"
                    f"{_pct_cell(m['total_growth_pct'])}"
                    f"{_pct_cell(m['deposit_growth_pct'])}"
                    f"{_pct_cell(m['investment_return_pct'])}</tr>"
                )
            breakdown_html = f"""
            <div class="table-scroll">
            <table>
                <tr><th>월</th><th>총증가율</th><th>입금기여</th><th>투자수익률</th></tr>
                {breakdown_rows}
            </table>
            </div>
            """
        else:
            report = engine.get_monthly_report(acc, year, month)
            period_label = f"{year}년 {month}월"
            breakdown_html = ""

        start_value = f"{report['start_value']:,.0f}" if report['start_value'] is not None else "—"
        end_value = f"{report['end_value']:,.0f}" if report['end_value'] is not None else "—"
        net_deposits = f"{report['net_deposits']:+,.0f}"

        sections_html += f"""
        <h3>{acc} — {period_label}</h3>
        <table class="summary">
            <tr><td>기초 평가금액</td><td>{start_value}</td></tr>
            <tr><td>기말 평가금액</td><td>{end_value}</td></tr>
            <tr><td>기간 순입금</td><td>{net_deposits}</td></tr>
            <tr><td>총 증가율</td>{_pct_cell(report['total_growth_pct'])}</tr>
            <tr><td>입금 기여율</td>{_pct_cell(report['deposit_growth_pct'])}</tr>
            <tr><td>투자 수익률</td>{_pct_cell(report['investment_return_pct'])}</tr>
        </table>
        {breakdown_html}
        """

    # 이전/다음 이동 링크
    if mode == "yearly":
        prev_url = f"/report/view?account_type={quote(account_type)}&year={year - 1}&mode=yearly"
        next_url = f"/report/view?account_type={quote(account_type)}&year={year + 1}&mode=yearly"
    else:
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        prev_url = f"/report/view?account_type={quote(account_type)}&year={prev_year}&month={prev_month}"
        next_url = f"/report/view?account_type={quote(account_type)}&year={next_year}&month={next_month}"

    toggle_mode = "yearly" if mode != "yearly" else "monthly"
    toggle_label = "연간 보기" if mode != "yearly" else "월간 보기"
    toggle_url = f"/report/view?account_type={quote(account_type)}&year={year}&mode={toggle_mode}"

    default_chart_account = account_type if account_type in ACCOUNT_TYPES else ACCOUNT_TYPES[0]
    asset_trend_chart = _render_asset_trend_chart(default_chart_account)
    comprehensive_review_html = _render_comprehensive_review_section(engine)

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>성과 리포트</title>
        <style>
            body {{ font-family: sans-serif; padding: 16px; }}
            .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
            table {{ border-collapse: collapse; width: 100%; min-width: 400px; font-size: 14px; margin-bottom: 8px; }}
            th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: right; white-space: nowrap; }}
            th:first-child, td:first-child {{ text-align: left; white-space: normal; }}
            th {{ background: #f4f4f5; }}
            td.up {{ color: #d92626; }}
            td.down {{ color: #2563eb; }}
            table.summary {{ min-width: 0; max-width: 360px; }}
            .nav {{ margin: 12px 0; }}
            .nav a {{ margin-right: 12px; }}
        </style>
    </head>
    <body>
        <h2>성과 리포트</h2>
        <div class="nav">
            <a href="{prev_url}">◀ 이전</a>
            <a href="{next_url}">다음 ▶</a>
            <a href="{toggle_url}">{toggle_label}</a>
            <a href="/report/deposit">입금 기록</a>
        </div>
        <h2>Summary</h2>
        {sections_html}
        <p style="color:#888; font-size:12px;">
            투자수익률은 Simple Dietz 근사치입니다(정밀 XIRR 아님). 스냅샷 적재 시작일 이전 데이터는 없습니다.
        </p>
        <h2>종합 점검</h2>
        {comprehensive_review_html}
        <h2>자산 추이</h2>
        {asset_trend_chart}
    </body>
    </html>
    """


def _render_deposit_form_page(db: Session, message: str = "", edit_flow: dict = None) -> str:
    engine = PerformanceReportEngine(db)
    flows = engine.get_cash_flows(limit=30)

    rows_html = ""
    for f in flows:
        rows_html += (
            f"<tr><td>{f['flow_date']}</td><td>{f['account_type']}</td>"
            f"<td>{f['amount']:+,.0f}</td><td>{f['memo'] or ''}</td>"
            f"<td>"
            f"<a href=\"/report/deposit?edit_id={f['id']}\"><button type=\"button\">수정</button></a> "
            f"<form method=\"post\" action=\"/report/deposit/delete\" style=\"display:inline\" "
            f"onsubmit=\"return confirm('삭제하시겠습니까?')\">"
            f"<input type=\"hidden\" name=\"flow_id\" value=\"{f['id']}\">"
            f"<button type=\"submit\">삭제</button></form></td></tr>"
        )

    message_html = f'<p class="msg">{message}</p>' if message else ""
    account_select = _account_options_html(edit_flow["account_type"] if edit_flow else "")
    today = date.today().isoformat()

    form_title = "수정" if edit_flow else "입금/출금 추가"
    form_action = "/report/deposit/update" if edit_flow else "/report/deposit/add"
    flow_date_value = edit_flow["flow_date"] if edit_flow else today
    amount_value = f' value="{edit_flow["amount"]:g}"' if edit_flow else ""
    memo_value = f' value="{edit_flow["memo"] or ""}"' if edit_flow else ""
    flow_id_field = f'<input type="hidden" name="flow_id" value="{edit_flow["id"]}">' if edit_flow else ""
    cancel_link = '<a href="/report/deposit"><button type="button">취소</button></a>' if edit_flow else ""

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>입금 기록</title>
        <style>
            body {{ font-family: sans-serif; padding: 16px; }}
            .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
            table {{ border-collapse: collapse; width: 100%; min-width: 400px; font-size: 14px; }}
            th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: right; white-space: nowrap; }}
            th:first-child, td:first-child {{ text-align: left; white-space: normal; }}
            th {{ background: #f4f4f5; }}
            form.add-form {{ margin-top: 20px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
            form.add-form input, form.add-form select {{ padding: 6px; font-size: 14px; }}
            button {{ padding: 6px 12px; font-size: 14px; }}
            .msg {{ color: #16a34a; font-weight: bold; }}
            .nav {{ margin: 12px 0; }}
        </style>
    </head>
    <body>
        <h2>입금 기록</h2>
        <div class="nav"><a href="/report/view">성과 리포트로</a></div>
        {message_html}
        <div class="table-scroll">
        <table>
            <tr><th>날짜</th><th>계좌</th><th>금액</th><th>메모</th><th></th></tr>
            {rows_html if rows_html else '<tr><td colspan="5">기록 없음</td></tr>'}
        </table>
        </div>

        <h3>{form_title}</h3>
        <form class="add-form" method="post" action="{form_action}">
            {flow_id_field}
            <input type="date" name="flow_date" value="{flow_date_value}" required>
            <select name="account_type" required>{account_select}</select>
            <input type="number" step="any" name="amount" placeholder="금액 (출금은 음수)"{amount_value} required>
            <input type="text" name="memo" placeholder="메모 (선택)"{memo_value}>
            <button type="submit">저장</button>
            {cancel_link}
        </form>
        <p style="color:#888; font-size:12px;">
            양수=입금, 음수=출금. 표의 "수정" 버튼을 누르면 기존 값이 채워집니다.
        </p>
    </body>
    </html>
    """


@app.get("/report/view", response_class=HTMLResponse)
async def report_view_page(
    request: Request,
    account_type: str = "",
    year: int = 0,
    month: int = 0,
    mode: str = "monthly",
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    today = date.today()
    year = year or today.year
    month = month or today.month
    return _render_performance_report_page(db, account_type, year, month, mode)


@app.get("/report/ohlc")
async def report_ohlc(
    request: Request,
    account_type: str = "",
    period: str = "monthly",
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    if account_type not in ACCOUNT_TYPES:
        account_type = ACCOUNT_TYPES[0]
    if period not in ("weekly", "monthly", "yearly"):
        period = "monthly"

    engine = PerformanceReportEngine(db)
    ohlc = engine.get_ohlc_series(account_type, period)
    data = []
    for pt in ohlc:
        d = date.fromisoformat(pt["date"])
        x_ms = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
        data.append({
            "x": x_ms,
            "y": [round(pt["o"] / 10000, 1), round(pt["h"] / 10000, 1), round(pt["l"] / 10000, 1), round(pt["c"] / 10000, 1)],
        })
    return JSONResponse({"data": data})


@app.get("/report/deposit", response_class=HTMLResponse)
async def report_deposit_page(request: Request, message: str = "", edit_id: int = 0, db: Session = Depends(get_db)):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    engine = PerformanceReportEngine(db)
    edit_flow = engine.get_cash_flow(edit_id) if edit_id else None
    return _render_deposit_form_page(db, message=message, edit_flow=edit_flow)


@app.post("/report/deposit/add")
async def report_deposit_add(
    request: Request,
    flow_date: date = Form(...),
    account_type: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    engine = PerformanceReportEngine(db)
    engine.record_cash_flow(flow_date, account_type, amount, memo)
    return RedirectResponse(
        url=f"/report/deposit?message={quote('저장되었습니다')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/report/deposit/update")
async def report_deposit_update(
    request: Request,
    flow_id: int = Form(...),
    flow_date: date = Form(...),
    account_type: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    engine = PerformanceReportEngine(db)
    engine.update_cash_flow(flow_id, flow_date, account_type, amount, memo)
    return RedirectResponse(
        url=f"/report/deposit?message={quote('수정되었습니다')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/report/deposit/delete")
async def report_deposit_delete(
    request: Request,
    flow_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if not _has_valid_session(request):
        return RedirectResponse(url="/portfolio/login", status_code=status.HTTP_303_SEE_OTHER)
    engine = PerformanceReportEngine(db)
    engine.delete_cash_flow(flow_id)
    return RedirectResponse(
        url=f"/report/deposit?message={quote('삭제되었습니다')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level=LOG_LEVEL.lower())
