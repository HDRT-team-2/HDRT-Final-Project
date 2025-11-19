<script setup lang="ts">
import BattlefieldMap from '@/components/map/BattlefieldMap.vue';
import SideBar from '@/layouts/SideBar.vue';

// 좌측 사이드바 설정
const leftSideBar = {
    contents: [
        'StatusReport',
        'Positions',
        'CommandPanel'
        
    ],
    col: [1, 1, 8]
}

// 우측 사이드바 설정  
const rightSideBar = {
    contents: [
        'DetectedObjects',
        'SituationLog',
        'FireSchedule',
    ],
    col: [2, 6, 4]
}

// 전체 레이아웃 비율 설정
const layoutConfig = {
    leftSidebar: 3,    // 좌측 사이드바 비율
    map: 7,            // 맵 영역 비율  
    rightSidebar: 3    // 우측 사이드바 비율
    // 총합: 3:6:3 = 25% : 50% : 25%
}

// Flex 스타일 생성 함수
const getFlexStyle = (ratio: number) => ({
    flexGrow: ratio,
    flexShrink: 0,
    flexBasis: 0
})

</script>
<template>
    <div class="flex">
        <!-- 좌측 사이드바 -->
        <div :style="getFlexStyle(layoutConfig.leftSidebar)" class="bg-white">
            <SideBar 
                class="h-full" 
                :contents="leftSideBar.contents" 
                :col="leftSideBar.col" 
            />
        </div>
        
        <!-- 맵 영역 -->
        <div :style="getFlexStyle(layoutConfig.map)" class="bg-gray-200">
            <BattlefieldMap class="h-full" />
        </div>
        
        <!-- 우측 사이드바 -->
        <div :style="getFlexStyle(layoutConfig.rightSidebar)" class="bg-white">
            <SideBar 
                class="h-full" 
                :contents="rightSideBar.contents" 
                :col="rightSideBar.col" 
            />
        </div>
    </div>
</template>