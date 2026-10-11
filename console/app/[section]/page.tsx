import Workspace from "@/components/Workspace";

const valid = ["dashboard","models","deployments","datasets","training","evaluations","audit","settings"];
export async function generateStaticParams() { return valid.map(section => ({ section })); }
export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  return <Workspace section={valid.includes(section) ? section : "dashboard"} />;
}
