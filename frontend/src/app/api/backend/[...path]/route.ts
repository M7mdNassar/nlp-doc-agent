import { proxyRequest } from "@/lib/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

async function handle(request: Request, context: Context) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}
export { handle as GET, handle as POST, handle as DELETE };
