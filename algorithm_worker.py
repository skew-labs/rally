"""Small scoring language: interpreted AST, never eval/exec or user Python."""
import ast
import json
import math
import resource
import sys

FEATURES={'recency','likes','replies','watched','following','has_media','is_agent','has_asset'}


def parse(source):
    if not isinstance(source,str) or not 1<=len(source)<=1000:raise ValueError('Use a formula under 1,000 characters')
    tree=ast.parse(source,mode='eval')
    nodes=list(ast.walk(tree))
    if len(nodes)>100:raise ValueError('Formula is too complex')
    allowed=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.BoolOp,ast.Compare,ast.IfExp,ast.Name,ast.Load,ast.Constant,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.USub,ast.UAdd,ast.And,ast.Or,ast.Not,ast.Eq,ast.NotEq,ast.Lt,ast.LtE,ast.Gt,ast.GtE)
    for n in nodes:
        if not isinstance(n,allowed):raise ValueError('Use numbers, features, arithmetic and conditions only')
        if isinstance(n,ast.Name) and n.id not in FEATURES:raise ValueError('Unknown feature: '+n.id)
        if isinstance(n,ast.Constant) and (type(n.value) not in (int,float,bool) or not math.isfinite(n.value) or abs(n.value)>1000000):raise ValueError('Number is out of range')
    def depth(n):return 1+max((depth(c) for c in ast.iter_child_nodes(n)),default=0)
    if depth(tree)>16:raise ValueError('Formula is too deeply nested')
    return tree.body


def evaluate(n, f):
    if isinstance(n,ast.Constant):return float(n.value)
    if isinstance(n,ast.Name):return f[n.id]
    if isinstance(n,ast.IfExp):return evaluate(n.body if evaluate(n.test,f) else n.orelse,f)
    if isinstance(n,ast.UnaryOp):
        v=evaluate(n.operand,f)
        return -v if isinstance(n.op,ast.USub) else not v if isinstance(n.op,ast.Not) else v
    if isinstance(n,ast.BoolOp):
        vals=[bool(evaluate(v,f)) for v in n.values]
        return all(vals) if isinstance(n.op,ast.And) else any(vals)
    if isinstance(n,ast.Compare):
        left=evaluate(n.left,f)
        for op,node in zip(n.ops,n.comparators):
            right=evaluate(node,f)
            ok=(left==right if isinstance(op,ast.Eq) else left!=right if isinstance(op,ast.NotEq) else left<right if isinstance(op,ast.Lt) else left<=right if isinstance(op,ast.LtE) else left>right if isinstance(op,ast.Gt) else left>=right)
            if not ok:return False
            left=right
        return True
    if isinstance(n,ast.BinOp):
        a,b=evaluate(n.left,f),evaluate(n.right,f)
        if isinstance(n.op,ast.Add):value=a+b
        elif isinstance(n.op,ast.Sub):value=a-b
        elif isinstance(n.op,ast.Mult):value=a*b
        else:
            if abs(b)<1e-12:raise ValueError('Division by zero')
            value=a/b
        if not math.isfinite(value) or abs(value)>1e12:raise ValueError('Score is out of range')
        return value
    raise ValueError('Unsupported expression')


if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CPU,(1,1))
    resource.setrlimit(resource.RLIMIT_AS,(96*1024*1024,96*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(16,16))
    try:
        value=json.loads(sys.stdin.buffer.read(65537))
        tree=parse(value['expression']);items=value.get('items',[])
        if len(items)>100:raise ValueError('Too many candidates')
        result=[]
        for item in items:
            f=item['features']
            if set(f)!=FEATURES or not all(type(v) in (int,float,bool) and math.isfinite(v) and abs(v)<=1e6 for v in f.values()):raise ValueError('Invalid features')
            result.append({'id':item['id'],'score':float(evaluate(tree,f))})
        print(json.dumps({'scores':result},allow_nan=False))
    except Exception as e:print(json.dumps({'error':str(e)[:180]}));sys.exit(1)
