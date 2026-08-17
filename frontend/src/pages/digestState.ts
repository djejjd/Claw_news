import { computed, ref } from "vue";

import { PublicApiError } from "../api/client";
import { getCurrentDigest, type DigestPublic } from "../api/digest";

export function useDigestState() {
  const digest = ref<DigestPublic | null>(null);
  const error = ref<PublicApiError | null>(null);
  const isLoading = ref(true);

  const sortedItems = computed(() =>
    [...(digest.value?.items ?? [])].sort((left, right) => left.position - right.position),
  );
  const sortedProjects = computed(() =>
    [...(digest.value?.github_projects ?? [])].sort((left, right) => left.position - right.position),
  );

  const failureMessage = computed(() => {
    if (error.value?.code === "network_error") {
      return "网络连接不可用，请检查网络后重试。";
    }
    if (error.value?.status === 503) {
      return "日报服务暂不可用，请稍后重试。";
    }
    return "日报加载失败，请稍后重试。";
  });

  async function loadDigest() {
    isLoading.value = true;
    // 新请求开始时清空旧内容，避免错误显示为上一次日报的成功结果。
    digest.value = null;
    error.value = null;
    try {
      digest.value = await getCurrentDigest();
    } catch (caught) {
      error.value =
        caught instanceof PublicApiError
          ? caught
          : new PublicApiError(0, "network_error", "公共内容服务暂不可用");
    } finally {
      isLoading.value = false;
    }
  }

  return { digest, error, failureMessage, isLoading, loadDigest, sortedItems, sortedProjects };
}
