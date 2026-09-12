from __future__ import annotations
from datetime import date


def diff(old_bis:list, new_bis:list, old_recipes:dict, new_recipes:dict):
    ob={x['name']:x for x in old_bis}; nb={x['name']:x for x in new_bis}
    added=sorted(set(nb)-set(ob)); removed=sorted(set(ob)-set(nb))
    hero_changes=[]
    for name in sorted(set(ob)&set(nb)):
        a=set(ob[name].get('heroes',[])); b=set(nb[name].get('heroes',[]))
        if a!=b: hero_changes.append({'name':name,'added':sorted(b-a),'removed':sorted(a-b)})
    recipe_changes=[]
    for name in sorted(set(old_recipes)&set(new_recipes)):
        if old_recipes[name]!=new_recipes[name]: recipe_changes.append(name)
    return {'added':added,'removed':removed,'hero_changes':hero_changes,'recipe_changes':recipe_changes}


def render_entry(changes:dict, stamp:str|None=None)->str:
    stamp=stamp or date.today().isoformat()
    if not any(changes.values()): return ''
    out=[f'## {stamp}','']
    if changes['added']:
        out+=['### Nuevos objetos BiS']+[f'- {x}' for x in changes['added']]+['']
    if changes['removed']:
        out+=['### Objetos que dejan de ser BiS']+[f'- {x}' for x in changes['removed']]+['']
    if changes['hero_changes']:
        out+=['### Cambios de clase/héroe']
        for x in changes['hero_changes']:
            bits=[]
            if x['added']: bits.append('+'+', '.join(x['added']))
            if x['removed']: bits.append('-'+', '.join(x['removed']))
            out.append(f"- {x['name']}: {'; '.join(bits)}")
        out.append('')
    if changes['recipe_changes']:
        out+=['### Recetas modificadas']+[f'- {x}' for x in changes['recipe_changes']]+['']
    return '\n'.join(out).rstrip()+'\n\n'
