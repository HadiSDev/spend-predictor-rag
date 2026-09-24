import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { useAuth, useSignIn } from '@clerk/tanstack-react-start'
import { BarChart3 } from 'lucide-react'
import {
  Button,
  Card,
  CodeInput,
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Separator,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTab,
} from '#/components/ui'
import { GOOGLE_OAUTH_ENABLED } from '#/lib/env'

export const Route = createFileRoute('/sign-in')({ component: SignInPage })

type SignInResource = ReturnType<typeof useSignIn>['signIn']

/** A Clerk error (from a future-API `{ error }` result) → user-facing message. */
function clerkErrorMessage(err: { longMessage?: string; message?: string } | null): string {
  return err?.longMessage ?? err?.message ?? 'Something went wrong. Please try again.'
}

interface PanelProps {
  signIn: SignInResource
  setError: (msg: string | null) => void
  /** Activate the session once the sign-in reaches `complete`, then navigate. */
  finish: () => Promise<void>
}

function PasswordPanel({ signIn, setError, finish }: PanelProps) {
  const form = useForm<{ email: string; password: string }>({
    defaultValues: { email: '', password: '' },
  })

  async function onSubmit(values: { email: string; password: string }) {
    if (!signIn) return
    setError(null)
    const { error } = await signIn.password({
      identifier: values.email,
      password: values.password,
    })
    if (error) {
      setError(clerkErrorMessage(error))
      return
    }
    await finish()
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="email"
          rules={{ required: 'Email is required' }}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" placeholder="you@company.com" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          rules={{ required: 'Password is required' }}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Password</FormLabel>
              <FormControl>
                <Input type="password" autoComplete="current-password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={form.formState.isSubmitting} className="w-full">
          {form.formState.isSubmitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </Form>
  )
}

function EmailCodePanel({ signIn, setError, finish }: PanelProps) {
  const [step, setStep] = React.useState<'email' | 'code'>('email')
  const [email, setEmail] = React.useState('')
  const emailForm = useForm<{ email: string }>({ defaultValues: { email: '' } })
  const codeForm = useForm<{ code: string }>({ defaultValues: { code: '' } })

  async function sendCode(values: { email: string }) {
    if (!signIn) return
    setError(null)
    const { error } = await signIn.emailCode.sendCode({ emailAddress: values.email })
    if (error) {
      setError(clerkErrorMessage(error))
      return
    }
    setEmail(values.email)
    setStep('code')
  }

  async function verify(values: { code: string }) {
    if (!signIn) return
    setError(null)
    const { error } = await signIn.emailCode.verifyCode({ code: values.code })
    if (error) {
      setError(clerkErrorMessage(error))
      return
    }
    await finish()
  }

  function reset() {
    setError(null)
    codeForm.reset()
    setStep('email')
  }

  if (step === 'email') {
    return (
      <Form {...emailForm}>
        <form onSubmit={emailForm.handleSubmit(sendCode)} className="flex flex-col gap-4">
          <FormField
            control={emailForm.control}
            name="email"
            rules={{ required: 'Email is required' }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" placeholder="you@company.com" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" disabled={emailForm.formState.isSubmitting} className="w-full">
            {emailForm.formState.isSubmitting ? 'Sending code…' : 'Email me a code'}
          </Button>
        </form>
      </Form>
    )
  }

  return (
    <Form {...codeForm}>
      <form onSubmit={codeForm.handleSubmit(verify)} className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          We sent a code to <span className="font-medium text-foreground">{email}</span>.
        </p>
        <FormField
          control={codeForm.control}
          name="code"
          rules={{ required: 'Enter the code from your email' }}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Verification code</FormLabel>
              <FormControl>
                <CodeInput
                  {...field}
                  onComplete={() => {
                    // A pasted code verifies with no further click. Guarded on
                    // isSubmitting so a re-completion mid-flight cannot submit
                    // twice; the button remains the retry path.
                    if (!codeForm.formState.isSubmitting) {
                      void codeForm.handleSubmit(verify)()
                    }
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={codeForm.formState.isSubmitting} className="w-full">
          {codeForm.formState.isSubmitting ? 'Verifying…' : 'Verify & sign in'}
        </Button>
        <button
          type="button"
          onClick={reset}
          className="text-sm text-muted-foreground underline-offset-2 outline-none hover:text-foreground hover:underline focus-visible:text-foreground"
        >
          Use a different email
        </button>
      </form>
    </Form>
  )
}

function SignInPage() {
  const { signIn, fetchStatus } = useSignIn()
  // Treat a pending (no-active-org) session as signed-in so we forward to the
  // app, where the `_authed` layout resolves the organization task.
  const { isLoaded, isSignedIn } = useAuth({ treatPendingAsSignedOut: false })
  const navigate = useNavigate()
  const [formError, setFormError] = React.useState<string | null>(null)
  const [oauthPending, setOauthPending] = React.useState(false)

  // An already-signed-in session shouldn't sit on the sign-in screen. Client
  // navigation only — never a full reload (that resets Clerk and causes a
  // sign-in ⇄ dashboard flash loop).
  React.useEffect(() => {
    if (isLoaded && isSignedIn) void navigate({ to: '/' })
  }, [isLoaded, isSignedIn, navigate])

  async function finish() {
    if (!signIn) return
    if (signIn.status !== 'complete') {
      setFormError(
        'Additional verification is required to finish signing in. Please contact your administrator.',
      )
      return
    }
    const { error } = await signIn.finalize()
    if (error) {
      setFormError(clerkErrorMessage(error))
      return
    }
    // Client-side navigation; the `_authed` layout gates on Clerk's reactive
    // client state (and activates the org for pending sessions).
    await navigate({ to: '/' })
  }

  async function signInWithGoogle() {
    if (!signIn) return
    setFormError(null)
    setOauthPending(true)
    const origin = window.location.origin
    const { error } = await signIn.sso({
      strategy: 'oauth_google',
      redirectUrl: `${origin}/sso-callback`,
      redirectCallbackUrl: `${origin}/sso-callback`,
    })
    if (error) {
      setOauthPending(false)
      setFormError(clerkErrorMessage(error))
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <div className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
            <BarChart3 className="size-5" />
          </div>
          <span className="font-display text-xl font-semibold tracking-tight">Spend Predictor</span>
        </div>

        <Card className="p-6">
          <div className="mb-5 space-y-1 text-center">
            <h1 className="font-display text-lg font-semibold tracking-tight">Sign in</h1>
            <p className="text-sm text-muted-foreground">Welcome back — sign in to continue.</p>
          </div>

          {formError ? (
            <div
              role="alert"
              className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {formError}
            </div>
          ) : null}

          <Tabs defaultValue="password" onValueChange={() => setFormError(null)}>
            <TabsList className="w-full">
              <TabsTab value="password" className="flex-1">
                Password
              </TabsTab>
              <TabsTab value="code" className="flex-1">
                Email code
              </TabsTab>
            </TabsList>
            <TabsPanel value="password">
              <PasswordPanel signIn={signIn} setError={setFormError} finish={finish} />
            </TabsPanel>
            <TabsPanel value="code">
              <EmailCodePanel signIn={signIn} setError={setFormError} finish={finish} />
            </TabsPanel>
          </Tabs>

          {GOOGLE_OAUTH_ENABLED ? (
            <>
              <div className="my-4 flex items-center gap-3">
                <Separator className="flex-1" />
                <span className="text-xs text-muted-foreground">or</span>
                <Separator className="flex-1" />
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                disabled={!signIn || oauthPending || fetchStatus === 'fetching'}
                onClick={signInWithGoogle}
              >
                Continue with Google
              </Button>
            </>
          ) : null}
        </Card>
      </div>
    </div>
  )
}
