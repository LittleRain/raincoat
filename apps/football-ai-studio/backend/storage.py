"""Disk accounting and narrowly scoped, regenerable frame cleanup."""
from pathlib import Path
from fastapi import HTTPException


def register_routes(app, store):
    def files():
        for path in store.data.rglob('*'):
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(store.data):
                yield path

    def preserved_refs():
        return {Path(r['local_reference_path']).resolve() for r in store.rows('SELECT local_reference_path FROM target_references')}

    def is_cache(path, refs):
        parts=path.relative_to(store.data).parts
        return len(parts)>=4 and parts[0]=='derived' and parts[2] in {'frames','analysis'} and path.resolve() not in refs

    @app.get('/api/storage')
    def usage():
        totals={k:0 for k in ('originals_bytes','derived_bytes','exports_bytes','cache_bytes','database_bytes','other_bytes')}
        refs=preserved_refs()
        for path in files():
            parts=path.relative_to(store.data).parts
            if is_cache(path,refs): category='cache_bytes'
            elif parts[0] in {'uploads','media'}: category='originals_bytes'
            elif parts[0]=='derived': category='derived_bytes'
            elif parts[0]=='exports': category='exports_bytes'
            elif parts[0].startswith('studio.sqlite3') or parts[0]=='backups': category='database_bytes'
            else: category='other_bytes'
            try:
                totals[category]+=path.stat().st_size
            except FileNotFoundError:
                pass
        return {**totals,'total_bytes':sum(totals.values()),'scope':'应用数据目录；外部引用原片不计入'}

    @app.post('/api/storage/cleanup')
    def cleanup():
        count=size=0
        # Match reference creation lock order: cache lock, then database transaction.
        with store.cache_lock, store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute("SELECT id FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                raise HTTPException(409,'请等待任务完成或取消后再清理帧缓存')
            refs=preserved_refs()
            for path in files():
                if is_cache(path,refs):
                    try:
                        size+=path.stat().st_size; path.unlink(); count+=1
                    except FileNotFoundError:
                        pass
        return {'removed_files':count,'removed_bytes':size,'preserved':'原片、代理、目标参考、审核、成片及AI费用请求缓存'}
