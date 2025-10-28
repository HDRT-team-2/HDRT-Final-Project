<script setup lang="ts">
import AppHeader from '@/layouts/AppHeader.vue';
import MainLayout from '@/layouts/MainLayout.vue';
import CommandPanel from '@/layouts/CommandPanel.vue';

import { useMockPositionWebSocket } from '@/composables/usePositionWebSocket'

// Mock WebSocket 시작
useMockPositionWebSocket()
</script>

<template>
    <div class="h-screen flex flex-col">
        <!-- 헤더: 고정 높이 -->
        <AppHeader class="h-10 flex-shrink-0" />
        
        <!-- 메인 레이아웃: 나머지 모든 공간 차지 -->
        <MainLayout class="flex-1 min-h-0" />
        
        <!-- 명령 패널: 고정 높이 -->
        <CommandPanel class="h-40 flex-shrink-0" />
    </div>
</template>