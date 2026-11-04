import {readdir, mkdir} from 'node:fs/promises';
import {join, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {NodeIO} from '@gltf-transform/core';
import {simplify, weld, prune, dedup} from '@gltf-transform/functions';
import {MeshoptSimplifier} from 'meshoptimizer';

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, '../../assets/so101/glb');
const target = join(here, '../../assets/so101/glb-lite');
const ratio = Number(process.env.RATIO ?? 0.25);
const error = Number(process.env.ERROR ?? 0.002);

const triangles = (document) =>
  document
    .getRoot()
    .listMeshes()
    .flatMap((mesh) => mesh.listPrimitives())
    .reduce((sum, prim) => sum + (prim.getIndices()?.getCount() ?? prim.getAttribute('POSITION').getCount()) / 3, 0);

await MeshoptSimplifier.ready;
await mkdir(target, {recursive: true});
const io = new NodeIO();
let before = 0;
let after = 0;
for (const name of (await readdir(source)).filter((file) => file.endsWith('.glb')).sort()) {
  const document = await io.read(join(source, name));
  const start = triangles(document);
  await document.transform(weld(), simplify({simplifier: MeshoptSimplifier, ratio, error}), dedup(), prune());
  const end = triangles(document);
  await io.write(join(target, name), document);
  before += start;
  after += end;
  console.log(`${name} ${start} -> ${end}`);
}
console.log(`unique parts ${before} -> ${after} triangles, ratio ${ratio}, error ${error}`);
