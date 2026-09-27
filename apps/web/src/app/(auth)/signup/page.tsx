import { AuthCard, AuthFooterLink, SignupForm } from "@/components/auth-forms";

export const metadata = { title: "Create organization" };

export default function SignupPage() {
  return (
    <AuthCard
      title="Create your organization"
      footer={
        <>
          Already have an account? <AuthFooterLink href="/login">Sign in</AuthFooterLink>
        </>
      }
    >
      <SignupForm />
    </AuthCard>
  );
}
