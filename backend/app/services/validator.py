"""知识校验服务 v2 — 对齐前端 noteValidator.js 的 7 类 × 4 级口径。

- 故障类型 7 种：factual_error 事实错误 / logic_error 逻辑矛盾 /
  relation_error 关系错误 / confusion 概念混淆 /
  imprecision 表述不精确（含碎片化断言）/ outdated 过时知识 / ambiguous 歧义术语
- 严重度 4 级：critical 严重 / major 主要 / minor 次要 / info 提示
- validate_content(content, db) 返回带全文偏移的 issue 列表：
  [{ type, severity, text, entity, description, correction, evidence,
     source, start, end, line, matchStart, matchEnd }]
  与前端 validateText 输出同构，可直接驱动编辑器波浪线 / ValidationPanel。
"""
import re
from typing import List, Dict, Optional, Tuple

# ==================== 严重度（4 级） ====================

SEVERITY_ORDER = ('critical', 'major', 'minor', 'info')

SEVERITIES = {
    'critical': {'code': 'critical', 'label': '严重', 'weight': 4, 'color': '#ff3b30', 'desc': '与知识库明确相悖，建议修正后保存'},
    'major':    {'code': 'major',    'label': '主要', 'weight': 3, 'color': '#ff8c1a', 'desc': '显著错误或易误导表述，建议修正'},
    'minor':    {'code': 'minor',    'label': '次要', 'weight': 2, 'color': '#d99a00', 'desc': '措辞/规范/精确度建议'},
    'info':     {'code': 'info',     'label': '提示', 'weight': 1, 'color': '#2f8fe0', 'desc': '信息性提示，可忽略'},
}

# 旧口径映射（兼容历史数据：error/warning/info、high/medium/low）
LEGACY_SEVERITY_MAP = {
    'error': 'critical', 'high': 'critical',
    'warning': 'major', 'medium': 'major',
    'low': 'minor',
    'info': 'info',
}


def normalize_severity(s) -> str:
    return LEGACY_SEVERITY_MAP.get(s) or (s if s in SEVERITIES else 'major')


# ==================== 故障类型（7 种） ====================

ERROR_TYPES = {
    'factual_error':  {'code': 'factual_error',  'label': '事实错误', 'severity': 'critical'},
    'logic_error':    {'code': 'logic_error',    'label': '逻辑矛盾', 'severity': 'critical'},
    'relation_error': {'code': 'relation_error', 'label': '关系错误', 'severity': 'major'},
    'confusion':      {'code': 'confusion',      'label': '概念混淆', 'severity': 'major'},
    'imprecision':    {'code': 'imprecision',    'label': '表述不精确', 'severity': 'minor'},
    'outdated':       {'code': 'outdated',       'label': '过时知识', 'severity': 'major'},
    'ambiguous':      {'code': 'ambiguous',      'label': '歧义术语', 'severity': 'minor'},
}

TYPE_ALIAS = {
    'invalid_fragment': 'imprecision',
    'nonstandard_naming': 'ambiguous',
    'fragment': 'imprecision',
    'knowledge_error': 'factual_error',
    'potential_confusion': 'confusion',
    'conflict': 'logic_error',
}


def normalize_type(t) -> str:
    return t if t in ERROR_TYPES else TYPE_ALIAS.get(t, 'factual_error')


# ==================== 规则表（与 noteValidator.js 对齐） ====================

# 知识库事实校验基准
KB_FACT_CHECKS = [
    (r'java.*解释型|java.*解释执行.*语言|java.*纯解释',
     'Java 是"编译为字节码 + JVM 解释执行"的混合型语言', '软件知识库 - 编程语言篇', 'critical'),
    (r'python.*编译型|python.*编译型语言',
     'Python 是解释型语言（.pyc 只是字节码缓存，本质仍解释执行）', '软件知识库 - 编程语言篇', 'critical'),
    (r'(javascript|java).*脚本.*(编译|编译型)',
     'JavaScript 是解释型/即时编译（JIT）语言，非传统编译型', '软件知识库 - 编程语言篇', 'major'),
    (r'http(?!s).*(?<!不)(?<!无)(?<!未)加密|http(?!s).*自带加密',
     'HTTP 本身不加密，HTTPS 通过 TLS 层实现加密', '软件知识库 - 网络全链路篇', 'critical'),
    (r'js.*单线程.*不能并发|node.*单线程.*不能并发|javascript.*不能并发',
     'JavaScript 是单线程事件循环，但异步 I/O + Worker Threads 可支持并发', '软件知识库 - 编程语言篇', 'major'),
    (r'sql.*不支持.*查询|sql.*不能.*复杂',
     'SQL 支持复杂查询（JOIN、子查询、窗口函数、CTE 等）', '软件知识库 - 数据库篇', 'major'),
    (r'jvm.*内存.*只有.*堆|jvm.*内存.*只有.*栈',
     'JVM 内存区域包括：堆、栈、方法区、程序计数器、本地方法栈', '软件知识库 - 编程语言篇', 'critical'),
    (r'栈.*存储.*堆|堆.*存储.*栈|gc.*回收.*栈|栈.*垃圾回收',
     '栈(Stack)与堆(Heap)是独立内存区域；GC 只作用于堆，栈由调用帧自动管理', '软件知识库 - 内存模型篇', 'critical'),
    (r'tcp.*无连接|udp.*面向连接',
     'TCP 是面向连接的协议，UDP 是无连接协议', '软件知识库 - 网络传输篇', 'critical'),
    (r'索引.*减慢.*查询|索引.*降低.*查询.*速度',
     '索引通过 B+树等结构加速查询，但会增加写入开销', '软件知识库 - 数据库篇', 'critical'),
]

# 过时术语映射表
OUTDATED_TERMS = [
    {'term': 'j2ee', 'replacement': 'Jakarta EE', 'since': '2018', 'reason': 'J2EE 已更名为 Jakarta EE'},
    {'term': 'j2se', 'replacement': 'Java SE', 'since': '2006', 'reason': 'J2SE 已更名为 Java SE'},
    {'term': 'j2me', 'replacement': 'Java ME', 'since': '2006', 'reason': 'J2ME 已更名为 Java ME'},
    {'term': 'applet', 'replacement': 'WebAssembly', 'since': '2016', 'reason': 'Java Applet 已废弃'},
    {'term': 'angularjs', 'replacement': 'Angular (2+)', 'since': '2016', 'reason': 'AngularJS 1.x 已停止维护'},
    {'term': 'python 2', 'replacement': 'Python 3', 'since': '2020', 'reason': 'Python 2 已于 2020 年停止维护'},
    {'term': 'ie浏览器', 'replacement': 'Edge', 'since': '2022', 'reason': 'IE 浏览器已于 2022 年退役'},
    {'term': 'svn', 'replacement': 'Git', 'since': '2015', 'reason': 'SVN 已基本被 Git 取代'},
]

# 常见概念混淆对（前端已给出双向条目，这里保留单向 + 双向检查由 locate_pair 决定先后）
CONFUSION_PAIRS = [
    ('javascript', 'java', '两者为不同编程语言，仅名称相似，无直接关系'),
    ('java', 'javascript', '两者为不同编程语言，仅名称相似，无直接关系'),
    ('c++', 'c', 'C++ 是 C 的超集，但两者是不同的语言'),
    ('html', 'css', 'HTML 是结构标记语言，CSS 是样式语言，两者并列而非包含'),
    ('编译器', '解释器', '编译器将源码整体转为机器码，解释器逐行执行，原理不同'),
    ('堆', '栈', '堆和栈是两种不同的内存区域，彼此平行，不存在包含关系'),
    ('tcp', 'udp', 'TCP 和 UDP 是传输层两种并列协议，不可混用'),
    ('http', 'https', 'HTTPS 是 HTTP 的安全版本（+TLS），两者有本质区别'),
    ('docker', '虚拟机', 'Docker 是容器技术，虚拟机是完整 OS 虚拟化，原理不同'),
    ('git', 'github', 'Git 是版本控制系统，GitHub 是代码托管平台'),
    ('sql', 'nosql', 'SQL 是关系型查询语言，NoSQL 是非关系型数据库'),
    ('进程', '线程', '进程是资源分配单位，线程是 CPU 调度单位，不可混用'),
    ('微服务', 'soa', '微服务是 SOA 的一种实现风格，但两者有架构差异'),
]

# 表述不精确 / 碎片化断言模式
IMPRECISION_PATTERNS = [
    (r'内存分为堆和栈', '请补充上下文，如"JVM内存分为堆和栈"', '补充"JVM"上下文'),
    (r'gc会暂停|gc.*暂停', 'GC 暂停需区分：Minor GC（短暂暂停）vs Full GC（长时间暂停）', '补充 GC 类型上下文'),
    (r'算法.*复杂度.*o\(1\)|算法.*复杂度.*o\(n\)', '请明确是"时间复杂度"还是"空间复杂度"', '补充复杂度类型'),
    (r'所以.*就是.*全部|所以.*都是', '"全部/都"这类全称断言缺少限定条件', '补充例外或适用边界'),
]

# 歧义术语表：命中但上下文无领域特征词时提示
AMBIGUOUS_TERMS = [
    ('spring', re.compile(r'编程|语言|框架|ioc|aop|依赖注入|bean|java')),
    ('python', re.compile(r'编程|语言|脚本|解释器|pip|代码')),
    ('ruby', re.compile(r'编程|语言|rails|gem|代码')),
    ('rust', re.compile(r'编程|语言|cargo|所有权|代码')),
    ('shell', re.compile(r'命令行|bash|脚本|terminal|代码')),
    ('c', re.compile(r'编程|语言|指针|编译|代码')),
    ('cookie', re.compile(r'http|浏览器|session|web|网页')),
    ('thread', re.compile(r'并发|多线程|进程|锁|代码')),
    ('pool', re.compile(r'连接池|线程池|资源|复用|代码')),
]

# 概念关联/包含/等价类表述（混淆提示的语境闸）
RELATION_WORDS = re.compile(r'相关|包含|属于|依赖|一种|类似|一样|差不多|就是|等价|相当于|基于')
# 模糊限定词
HEDGE_WORDS = re.compile(r'可能|大概|也许|或许|似乎|我觉得|我认为')
# 绝对性表述
CERTAINTY_WORDS = re.compile(r'一定|绝对|肯定|必然|永远')
# 不确定性限定
UNCERTAINTY_WORDS = re.compile(r'不一定|可能|也许|或许|未必')
# 关系倒置/否定表述（弱规则）
RELATION_DENY = re.compile(r'与.*无关|和.*没有.*关系|不属于|不是.*的(一部分|分支)')


def _escape_regex(s: str) -> str:
    return re.escape(s)


def _locate_term(text: str, term: str) -> Optional[Tuple[int, int]]:
    """词边界定位首个命中位置（英文词加边界；中文直接定位）。"""
    lower_text = text.lower()
    t = term.lower()
    if not t:
        return None
    if re.match(r'^[A-Za-z][A-Za-z0-9+._\-]*$', t):
        m = re.search(r'(^|[^A-Za-z0-9_])' + _escape_regex(t) + r'($|[^A-Za-z0-9_])', lower_text)
        if not m:
            return None
        start = m.start() + len(m.group(1))
        return (start, start + len(t))
    idx = lower_text.find(t)
    if idx == -1:
        return None
    return (idx, idx + len(t))


def _locate_pair(text: str, a: str, b: str) -> Optional[Tuple[int, int]]:
    """两者同时出现时返回先出现者的范围。"""
    ra = _locate_term(text, a)
    rb = _locate_term(text, b)
    if not ra or not rb:
        return None
    return ra if ra[0] <= rb[0] else rb


_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
_EN_WORD_RE = re.compile(r'[a-zA-Z]{2,}')
_ASCII_ONLY_RE = re.compile(r'^[a-zA-Z0-9_.\-\s]+$')


def _issue(sentence: str, details: dict) -> Dict:
    """构造句内 issue（含 matchStart/matchEnd 偏移），与前端 _makeIssue 对齐。"""
    type_code = normalize_type(details.get('type', 'factual_error'))
    meta = ERROR_TYPES[type_code]
    rng = details.get('range')
    if not rng:
        rng = (0, len(sentence) or 0)
    return {
        'type': type_code,
        'severity': normalize_severity(details.get('severity') or meta['severity']),
        'text': sentence,
        'entity': details.get('entity'),
        'description': details.get('description') or meta.get('label'),
        'correction': details.get('correction') or '',
        'evidence': details.get('evidence') or '',
        'source': details.get('source') or 'realtime',
        'matchStart': max(0, rng[0]),
        'matchEnd': max(0, rng[1]),
    }


def _entity_tokens(text: str) -> List[str]:
    """提取句中的候选实体词（中文 2+ 连续 + 英文词）。"""
    tokens = [w.lower() for w in re.findall(r'[\u4e00-\u9fff]{2,}', text)]
    tokens += [w.lower() for w in _EN_WORD_RE.findall(text)]
    return tokens


def _check_sentence(sentence: str, db=None) -> List[Dict]:
    """单句校验，返回带 matchStart/matchEnd 的 issue 列表（前端 validateSentence 规则移植）。"""
    issues: List[Dict] = []
    text = (sentence or '').strip()
    if not text or len(text) < 3:
        return issues
    lower_text = text.lower()

    # 1. 事实错误（与知识库明确相悖的断言）
    for pattern, correction, evidence, severity in KB_FACT_CHECKS:
        m = re.search(pattern, lower_text)
        if m:
            # 否定守卫：命中点前 6 字符内出现否定词（不/无/未/非）视为"并非如此"的正确表述
            hit_pos = m.end() - 1
            if not any(c in lower_text[max(0, hit_pos - 6):hit_pos] for c in '不无未非'):
                issues.append(_issue(text, {
                    'type': 'factual_error', 'severity': severity,
                    'description': '表述与知识库相悖',
                    'correction': correction, 'evidence': evidence,
                    'source': 'kb_fact_check',
                    'range': (m.start(), m.end() or m.start() + 1)
                }))

    # 2. 过时知识
    for info in OUTDATED_TERMS:
        r = _locate_term(text, info['term'])
        if r:
            issues.append(_issue(text, {
                'type': 'outdated', 'entity': info['term'],
                'description': '"%s" 已被 "%s" 取代（%s）' % (info['term'], info['replacement'], info['since']),
                'correction': '建议使用 "%s" 替代 "%s"' % (info['replacement'], info['term']),
                'evidence': info['reason'],
                'source': 'outdated_terms',
                'range': r
            }))

    # 3. 概念混淆：一对易混概念同现且句中有"关联/包含/等价"类表述
    for a, b, reason in CONFUSION_PAIRS:
        r = _locate_pair(text, a, b)
        if r and RELATION_WORDS.search(text):
            issues.append(_issue(text, {
                'type': 'confusion', 'entity': '%s/%s' % (a, b),
                'description': '"%s" 与 "%s" %s' % (a, b, reason),
                'correction': '请区分 "%s" 与 "%s"，避免混为一谈' % (a, b),
                'evidence': '软件知识库 - 概念辨析',
                'source': 'confusion_pairs',
                'range': r
            }))

    # 4. 歧义术语：命中多义词但上下文无领域特征词
    for term, ctx in AMBIGUOUS_TERMS:
        r = _locate_term(text, term)
        if r and not ctx.search(lower_text):
            issues.append(_issue(text, {
                'type': 'ambiguous', 'entity': term,
                'description': '"%s" 存在歧义（技术术语 vs 日常用语），上下文未明确指向' % term,
                'correction': '建议补充领域限定词，如 "%s 语言/框架/命令"' % term,
                'evidence': '软件知识库 - 术语表',
                'source': 'ambiguous_terms',
                'range': r
            }))

    # 5. 表述不精确 / 碎片化断言
    for pattern, msg, suggest in IMPRECISION_PATTERNS:
        m = re.search(pattern, lower_text)
        if m:
            issues.append(_issue(text, {
                'type': 'imprecision',
                'description': msg, 'correction': suggest,
                'evidence': '表述规范 - 知识完整性',
                'source': 'imprecision',
                'range': (m.start(), m.end() or m.start() + 1)
            }))
    cn_chars = len(_CJK_RE.findall(text))
    en_words = len(_EN_WORD_RE.findall(text))
    total_units = cn_chars + en_words
    if total_units < 8 and not _ASCII_ONLY_RE.match(text):
        issues.append(_issue(text, {
            'type': 'imprecision', 'entity': None,
            'description': '碎片化断言（有效信息约 %d 个字符/词），缺少上下文或来源' % total_units,
            'correction': '补充更多上下文或出处后再保存',
            'evidence': '内容完整性检测',
            'source': 'fragment_check'
        }))

    # 6. 逻辑矛盾：绝对性与不确定性同现
    if CERTAINTY_WORDS.search(text) and UNCERTAINTY_WORDS.search(text):
        issues.append(_issue(text, {
            'type': 'logic_error',
            'description': '句内同时出现绝对性断言与不确定性限定，存在逻辑矛盾',
            'correction': '删除相互矛盾的限定词，只保留确定口径',
            'evidence': '逻辑一致性检查',
            'source': 'internal_consistency'
        }))

    # 7. 关系错误：跨实体断言"完全无关"或方向倒置（弱规则）
    tokens = _entity_tokens(text)
    if len(tokens) >= 2 and RELATION_DENY.search(text):
        issues.append(_issue(text, {
            'type': 'relation_error',
            'entity': '/'.join(tokens[:2]),
            'description': '断言与知识库实体关系存疑：本体中相关实体被表述为无关',
            'correction': '请核实实体间真实关系后再断言',
            'evidence': '知识库桥接检测',
            'source': 'relation_hint'
        }))

    # 8. 知识库一致性（DB 存在时）：命中实体的对立术语同现 → 事实错误/概念混淆
    if db is not None:
        kb_hits = _check_kb_opposites(lower_text, tokens, db)
        issues.extend(kb_hits)

    return issues


def _check_kb_opposites(lower_text: str, tokens: List[str], db) -> List[Dict]:
    """查 KnowledgeBase 表：句中实体与其对立术语同现且带断言语境时告警。"""
    from app.models.models import KnowledgeBase
    issues: List[Dict] = []
    if not tokens:
        return issues
    try:
        rows = db.query(KnowledgeBase).filter(
            KnowledgeBase.entity.in_(tokens)
        ).all()
    except Exception:
        return issues
    for kb in rows:
        opposites = kb.opposite_terms or []
        if not opposites:
            continue
        for opp in opposites:
            opp_l = str(opp).lower()
            if opp_l in lower_text:
                has_assert = re.search(r'是|等于|就是|等价|属于|包含于', lower_text)
                if has_assert:
                    r = _locate_term(lower_text, kb.entity)
                    issues.append(_issue(lower_text, {
                        'type': 'factual_error', 'severity': 'critical',
                        'entity': kb.entity,
                        'description': '与知识库中"%s"的定义冲突（涉及对立术语"%s"）' % (kb.entity, opp),
                        'correction': kb.definition or '请核实"%s"与"%s"的真实关系' % (kb.entity, opp),
                        'evidence': kb.source or '知识库',
                        'source': 'kb_opposite',
                        'range': r or (0, len(kb.entity))
                    }))
                else:
                    r = _locate_term(lower_text, kb.entity)
                    issues.append(_issue(lower_text, {
                        'type': 'confusion', 'severity': 'major',
                        'entity': kb.entity,
                        'description': '句中同时出现"%s"及其对立概念"%s"，请注意区分' % (kb.entity, opp),
                        'correction': '核实该概念与"%s"的关系后重新表述' % opp,
                        'evidence': kb.source or '知识库',
                        'source': 'kb_opposite',
                        'range': r or (0, len(kb.entity))
                    }))
    return issues


def split_sentence_ranges(content: str) -> List[Dict]:
    """按句读/换行拆分，返回每个句子在全文中的起止与行号。

    @returns [{sentence, start, end, line}]
    """
    out: List[Dict] = []
    text = content or ''
    if not text.strip():
        return out
    re_chunk = re.compile(r'[^。！？!?\n]+[。！？!?]?|\n+')
    for m in re_chunk.finditer(text):
        raw = m.group(0)
        chunk_start = m.start()
        chunk_end = m.end()
        if not raw.strip():
            continue
        s0, s1 = chunk_start, chunk_end
        while s0 < s1 and text[s0].isspace():
            s0 += 1
        while s1 > s0 and text[s1 - 1].isspace():
            s1 -= 1
        if s0 >= s1:
            continue
        out.append({
            'sentence': text[s0:s1],
            'start': s0,
            'end': s1,
            'line': text[:s0].count('\n'),
        })
    return out


def validate_content(content: str, db=None) -> List[Dict]:
    """全文实时校验，返回带全文偏移的问题列表（前端 validateText 等价物）。

    @param content 笔记全文
    @param db      SQLAlchemy Session（提供时启用知识库对立术语一致性检查）
    @returns [{ type, severity, text, entity, description, correction,
                evidence, source, start, end, line, matchStart, matchEnd }]
    """
    issues: List[Dict] = []
    if not content or not content.strip():
        return issues
    for item in split_sentence_ranges(content):
        sentence = item['sentence']
        if len(sentence) < 3:
            continue
        for issue in _check_sentence(sentence, db):
            out = dict(issue)
            out['start'] = item['start'] + (issue.get('matchStart') or 0)
            out['end'] = item['start'] + (issue.get('matchEnd') or len(sentence))
            out['line'] = item['line']
            issues.append(out)
    issues.sort(key=lambda x: (x['start'], x['end']))
    return issues


def summarize(issues: List[Dict], sentence_count: Optional[int] = None) -> Dict:
    """统计汇总：与前端 preSaveValidation.summary 同口径（accuracy 为 0-100 分）。"""
    critical = sum(1 for i in issues if i['severity'] == 'critical')
    major = sum(1 for i in issues if i['severity'] == 'major')
    minor = sum(1 for i in issues if i['severity'] == 'minor')
    info = sum(1 for i in issues if i['severity'] == 'info')
    total = max(int(sentence_count or len(issues)), 1)
    deduction = sum({
        'critical': 1.0, 'major': 0.6, 'minor': 0.25, 'info': 0.05,
    }.get(i['severity'], 0) for i in issues)
    accuracy = max(0, min(100, round((1 - deduction / total) * 100)))
    return {
        'total': total,
        'passed': max(0, total - critical - major - minor - info),
        'errors': critical + major,
        'warnings': minor + info,
        'critical': critical,
        'major': major,
        'minor': minor,
        'info': info,
        'accuracy': accuracy,
    }
