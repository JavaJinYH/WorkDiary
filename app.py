import os
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'diary.json')
TAGS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'tags.json')

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3-coder:30b"
OLLAMA_TIMEOUT = 60

os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

if not os.path.exists(TAGS_FILE):
    default_tags = ["开发", "开会", "学习", "杂事", "其他"]
    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(default_tags, f)

def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_tags():
    with open(TAGS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_tags(tags):
    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/records', methods=['GET'])
def get_records():
    date = request.args.get('date')
    data = load_data()
    if date:
        return jsonify([r for r in data if r['date'] == date])
    return jsonify(data)

@app.route('/api/records', methods=['POST'])
def add_record():
    record = request.json
    record['id'] = datetime.now().strftime('%Y%m%d%H%M%S')
    record['date'] = datetime.now().strftime('%Y-%m-%d')
    record['created_at'] = datetime.now().isoformat()
    data = load_data()
    data.append(record)
    save_data(data)
    return jsonify({'success': True, 'record': record})

@app.route('/api/records/<record_id>', methods=['PUT'])
def update_record(record_id):
    update = request.json
    data = load_data()
    for i, r in enumerate(data):
        if r['id'] == record_id:
            data[i].update(update)
            break
    save_data(data)
    return jsonify({'success': True})

@app.route('/api/records/<record_id>', methods=['DELETE'])
def delete_record(record_id):
    data = load_data()
    data = [r for r in data if r['id'] != record_id]
    save_data(data)
    return jsonify({'success': True})

@app.route('/api/records/batch', methods=['POST'])
def batch_import():
    records = request.json
    save_data(records)
    return jsonify({'success': True, 'count': len(records)})

@app.route('/api/tags', methods=['GET'])
def get_tags():
    return jsonify(load_tags())

@app.route('/api/tags', methods=['POST'])
def add_tag():
    tag = request.json.get('tag')
    tags = load_tags()
    if tag and tag not in tags:
        tags.append(tag)
        save_tags(tags)
    return jsonify({'success': True, 'tags': tags})

@app.route('/api/summary/weekly', methods=['GET'])
def weekly_summary():
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    data = load_data()
    records = [r for r in data if datetime.strptime(r['date'], '%Y-%m-%d') >= week_start]
    return jsonify(generate_summary(records, '本周'))

@app.route('/api/summary/monthly', methods=['GET'])
def monthly_summary():
    today = datetime.now()
    month_start = today.replace(day=1)
    data = load_data()
    records = [r for r in data if datetime.strptime(r['date'], '%Y-%m-%d') >= month_start]
    return jsonify(generate_summary(records, '本月'))

@app.route('/api/summary/quarterly', methods=['GET'])
def quarterly_summary():
    today = datetime.now()
    quarter = (today.month - 1) // 3
    month_start = today.replace(month=quarter * 3 + 1, day=1)
    data = load_data()
    records = [r for r in data if datetime.strptime(r['date'], '%Y-%m-%d') >= month_start]
    return jsonify(generate_summary(records, '本季度'))

@app.route('/api/summary/yearly', methods=['GET'])
def yearly_summary():
    year_start = datetime.now().replace(month=1, day=1)
    data = load_data()
    records = [r for r in data if datetime.strptime(r['date'], '%Y-%m-%d') >= year_start]
    return jsonify(generate_summary(records, '今年'))

def generate_summary(records, period):
    tag_counts = {}
    for r in records:
        tag = r.get('tag', '未分类')
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    summary = f"{period}共记录 {len(records)} 条工作事项\n\n"
    summary += "【分类统计】\n"
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        summary += f"- {tag}: {count}条\n"
    
    summary += "\n【工作详情】\n"
    for r in records:
        summary += f"- {r['date']} [{r.get('tag', '未分类')}] {r.get('content', '')}\n"
    
    return {'summary': summary, 'tag_counts': tag_counts, 'total': len(records)}

def get_ai_summary(records, period_name):
    if not records:
        return "暂无记录可总结"
    
    tag_counts = {}
    for r in records:
        tag = r.get('tag', '未分类')
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    record_list = "\n".join([
        f"- {r['date']} [{r.get('tag', '未分类')}] {r.get('content', '')}"
        for r in records
    ])
    
    prompt = f"""请帮我总结以下工作记录，生成简洁的{period_name}工作报告。

【记录统计】
共{len(records)}条记录

【分类明细】
{', '.join([f'{tag}: {count}条' for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])])}

【工作详情】
{record_list}

请按以下格式生成总结：
1. 【{period_name}概述】- 1-2句话概括主要工作
2. 【分类统计】- 各类型工作数量和占比
3. 【主要成果】- 按类别列出完成的事项
4. 【建议】- 对下周/下月的工作建议

要求：简洁专业，适合直接用于周报/月报。"""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 500
                }
            },
            timeout=OLLAMA_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('response', '').strip()
        else:
            return None
            
    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        print(f"AI Summary Error: {e}")
        return None

@app.route('/api/ai/summary', methods=['POST'])
def ai_summary():
    data = request.json
    period_type = data.get('type', 'weekly')
    is_last = data.get('is_last', False)
    offset = -1 if is_last else 0
    
    today = datetime.now()
    
    if period_type == 'weekly':
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        period_start = week_start - timedelta(days=7)
        period_end = week_start
        period_name = '上周' if is_last else '本周'
    elif period_type == 'monthly':
        month_start = (today.replace(day=1) + timedelta(days=32 * offset)).replace(day=1)
        period_start = (month_start - timedelta(days=1)).replace(day=1)
        period_end = month_start
        period_name = '上月' if is_last else '本月'
    elif period_type == 'quarterly':
        current_quarter = (today.month - 1) // 3
        target_quarter = current_quarter + offset
        if target_quarter < 0:
            target_year = today.year - 1
            target_quarter = 4 + target_quarter
        elif target_quarter > 3:
            target_year = today.year + 1
            target_quarter = target_quarter - 4
        else:
            target_year = today.year
        quarter_start = today.replace(month=target_quarter * 3 + 1, day=1, year=target_year)
        if target_quarter == 0:
            period_start = quarter_start.replace(month=10, day=1, year=target_year - 1)
            period_end = quarter_start.replace(month=1, day=1)
        else:
            period_start = quarter_start.replace(month=(target_quarter - 1) * 3 + 1)
            period_end = quarter_start
        period_name = '上季度' if is_last else '本季度'
    elif period_type == 'yearly':
        year = today.year + offset
        period_start = today.replace(year=year, month=1, day=1)
        period_end = today.replace(year=year + 1, month=1, day=1)
        period_name = '去年' if is_last else '今年'
    else:
        week_start = today - timedelta(days=today.weekday())
        period_start = week_start - timedelta(days=7)
        period_end = week_start
        period_name = '上周'
    
    all_data = load_data()
    records = [
        r for r in all_data 
        if datetime.strptime(r['date'], '%Y-%m-%d') >= period_start 
        and datetime.strptime(r['date'], '%Y-%m-%d') < period_end
    ]
    
    basic_summary = generate_summary(records, period_name)
    
    ai_result = get_ai_summary(records, period_name)
    
    if ai_result:
        return jsonify({
            'success': True,
            'ai_summary': ai_result,
            'basic_summary': basic_summary['summary'],
            'tag_counts': basic_summary['tag_counts'],
            'total': basic_summary['total']
        })
    else:
        return jsonify({
            'success': False,
            'ai_summary': None,
            'basic_summary': basic_summary['summary'],
            'tag_counts': basic_summary['tag_counts'],
            'total': basic_summary['total'],
            'error': 'AI服务暂不可用，已返回原始总结'
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
