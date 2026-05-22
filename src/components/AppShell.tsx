"use client";

import { Footer, Header } from "@policyengine/ui-kit";

const navItems = [
  { label: "PolicyEngine", href: "https://policyengine.org/us" },
  { label: "Research", href: "https://policyengine.org/us/research" },
  { label: "API", href: "https://policyengine.org/us/api" },
];

export default function AppShell({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <>
      <Header
        navItems={navItems}
        currentCountry="us"
        countries={[{ id: "us", label: "United States" }]}
        logoHref="https://policyengine.org/us"
      />
      {children}
      <Footer
        links={[
          { href: "https://policyengine.org/us/research", text: "Research" },
          { href: "https://policyengine.org/us/model", text: "Model" },
          { href: "https://policyengine.org/us/api", text: "API" },
        ]}
      />
    </>
  );
}
