import type { APIRoute, GetStaticPaths } from "astro";
import { cropImages, renderCrop, type CropImage } from "../../lib/inspector-crops";

export const getStaticPaths: GetStaticPaths = () => cropImages().map((image) => ({ params: { crop: image.name }, props: { image } }));

export const GET: APIRoute = async ({ props }) => {
  const { image } = props as { image: CropImage };
  return new Response(await renderCrop(image), { headers: { "Content-Type": image.type } });
};
