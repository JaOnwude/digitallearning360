import { toast } from "sonner";
import { errorText } from "@/components/auth/steps";

/** Run a mutation and toast the outcome. Returns the result, or undefined on failure. */
export async function withToast<T>(work: Promise<T>, success?: string): Promise<T | undefined> {
  try {
    const result = await work;
    if (success) toast.success(success);
    return result;
  } catch (err) {
    toast.error(errorText(err));
    return undefined;
  }
}
