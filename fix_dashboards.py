import os, re

os.chdir(r'C:\Users\J_park\Shaker-MD-App\docs\dashboards')

channels_7 = ['bm-sellout', 'tamkeen-sellout', 'zagzoog-sellout', 'dhamin-sellout',
              'star-appliance-sellout', 'al-ghanem-sellout', 'al-shathri-sellout']

HELPER_FUNCTIONS = """
// ===== HELPER FUNCTIONS =====
function catBadge(c){
  if(!c) return '';
  var cls = c.includes('Split')?'cat-split':c.includes('Window')?'cat-window':c.includes('Concealed')?'cat-concealed':c.includes('Cassette')?'cat-cassette':'cat-floor';
  return '<span class="cat-badge '+cls+'">'+c+'</span>';
}
var fmt = function(n){ return n==null?'-':Number(n).toLocaleString(); };
"""

for channel in channels_7:
    filepath = channel + '/index.html'
    if not os.path.exists(filepath):
        print('MISS ' + channel)
        continue

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = []

    # FIX 1: Add catBadge() and fmt() before renderOverview
    if 'function catBadge(' not in content:
        content = content.replace(
            '// ===== TAB 1: OVERVIEW =====',
            HELPER_FUNCTIONS + '\n// ===== TAB 1: OVERVIEW ====='
        )
        changes.append('catBadge+fmt')

    # FIX 2: Fix selW
    if 'const weeks=[...selW].sort' in content:
        content = content.replace(
            'const weeks=[...selW].sort',
            'var selW=new Set(FILTER_STATE.w.size>0?WEEKS.filter(function(w){return !FILTER_STATE.w.has(w)}):WEEKS);\n  const weeks=[...selW].sort'
        )
        changes.append('selW')

    # FIX 3: Store chart instances
    for chart_id in ['c_weekly', 'c_monthly', 'c_cat_pie', 'c_cat_trend']:
        old_str = "new Chart(document.getElementById('" + chart_id + "')"
        new_str = "_charts['" + chart_id + "']=new Chart(document.getElementById('" + chart_id + "')"
        if old_str in content and new_str not in content:
            content = content.replace(old_str, new_str, 1)
            changes.append('chart_' + chart_id)

    # FIX 4: Guard D.models
    if 'D.models.find' in content:
        content = content.replace('D.models.find', '(D.models||[]).find')
        changes.append('D.models guard')

    # FIX 5: Fix orphan </div> in overview pane
    content = re.sub(
        r'(id="pane-overview">)\s*\n<span[^>]*id="ov_filter_info"[^>]*></span>\s*\n<!-- Filters -->\s*\n\s*\n\s*\n\s*</div>\s*\n\s*<button',
        r'\1\n<span class="filter-count" id="ov_filter_info" style="display:block;padding:4px 0;font-size:11px;color:var(--muted)"></span>\n  <button',
        content
    )

    # Fix trend pane orphan divs
    content = re.sub(
        r'(id="pane-trend">)\s*\n<!-- Filters -->\s*\n\s*\n\s*\n\s*</div>',
        r'\1',
        content
    )

    # Fix ranking pane orphan divs
    content = re.sub(
        r'(id="pane-ranking">)\s*\n<!-- Filters -->\s*\n\s*\n\s*\n\s*</div>',
        r'\1',
        content
    )
    changes.append('orphan_divs')

    # FIX 6: Add rank_search event listener
    if "getElementById('rank_search').addEventListener" not in content:
        old_init = "if(typeof renderOverview==='function') renderOverview();"
        new_init = old_init + "\nvar _rs=document.getElementById('rank_search');if(_rs)_rs.addEventListener('input',function(){if(typeof renderRanking==='function')renderRanking()});"
        content = content.replace(old_init, new_init, 1)
        changes.append('rank_search')

    # FIX 7: Guard m.n
    if "m.n.toLowerCase()" in content:
        content = content.replace("m.n.toLowerCase()", "(m.n||m.s||'').toLowerCase()")
        changes.append('m.n guard')

    # FIX 8: Add .mb-4 CSS
    if '.mb-4' not in content and 'class="card mb-4"' in content:
        content = content.replace(
            '@media(max-width:900px)',
            '.mb-4{margin-bottom:16px}\n@media(max-width:900px)'
        )
        changes.append('mb-4')

    # FIX 9: Fix Dhamin dn class
    if channel == 'dhamin-sellout':
        content = content.replace('class="kpi-sub dn"', 'class="kpi-sub up"')
        changes.append('dn_fix')

    # FIX 10: Remove duplicate renderOverview call after Chart.register
    content = re.sub(
        r'Chart\.register\(ChartDataLabels\);\s*\nrenderOverview\(\);',
        'Chart.register(ChartDataLabels);',
        content
    )
    changes.append('dup_render')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print('OK ' + channel + ': ' + ', '.join(changes))

# === BH FIXES ===
bh_path = 'bh-sellout/index.html'
if os.path.exists(bh_path):
    with open(bh_path, 'r', encoding='utf-8') as f:
        content = f.read()

    bh_changes = []

    # Guard D.dims.sales_types
    if "D.dims.sales_types.filter" in content:
        content = content.replace("D.dims.sales_types.filter", "(D.dims.sales_types||[]).filter")
        bh_changes.append('sales_types')

    # Guard D.price in functions
    for func in ['renderCatPriceBtns', 'renderModelPriceBtns', 'renderPriceTable']:
        marker = 'function ' + func + '(){'
        if marker in content:
            parts = content.split(marker, 1)
            if len(parts) == 2 and 'if(!D.price)return;' not in parts[1][:50]:
                content = parts[0] + marker + 'if(!D.price)return;' + parts[1]
                bh_changes.append('D.price_' + func)

    # Guard price init calls
    if 'renderCatPriceBtns();\nrenderModelPriceBtns();' in content:
        content = content.replace(
            'renderCatPriceBtns();\nrenderModelPriceBtns();',
            'if(D.price){renderCatPriceBtns();\nrenderModelPriceBtns();}'
        )
        bh_changes.append('price_init')

    # Fix missing CSS semicolon in price table
    content = re.sub(
        r'color:\$\{mc\}font-weight',
        r'color:${mc};font-weight',
        content
    )
    bh_changes.append('css_semicolon')

    # Guard r.name
    content = content.replace('name: r.name,', 'name: r.name||r.s||r.code,')
    bh_changes.append('r.name')

    with open(bh_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print('OK BH: ' + ', '.join(bh_changes))
