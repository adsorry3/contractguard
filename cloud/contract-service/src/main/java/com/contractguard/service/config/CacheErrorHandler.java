package com.contractguard.service.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.Cache;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.context.annotation.Configuration;

/**
 * 缓存降级处理：Redis 挂掉时，缓存读写失败只打 warning、不抛异常。
 * 这样 @Cacheable 会自动回源数据库，接口照常返回数据，只是慢一点。
 */
@Slf4j
@Configuration
public class CacheErrorHandler implements CachingConfigurer {

    @Override
    public org.springframework.cache.interceptor.CacheErrorHandler errorHandler() {
        return new org.springframework.cache.interceptor.CacheErrorHandler() {

            @Override
            public void handleCacheGetError(RuntimeException exception, Cache cache, Object key) {
                log.warn("缓存读取失败，已降级走数据库：cache={}, key={}, err={}",
                        cache.getName(), key, exception.getMessage());
            }

            @Override
            public void handleCachePutError(RuntimeException exception, Cache cache, Object key, Object value) {
                log.warn("缓存写入失败：cache={}, key={}, err={}",
                        cache.getName(), key, exception.getMessage());
            }

            @Override
            public void handleCacheEvictError(RuntimeException exception, Cache cache, Object key) {
                log.warn("缓存删除失败：cache={}, key={}, err={}",
                        cache.getName(), key, exception.getMessage());
            }

            @Override
            public void handleCacheClearError(RuntimeException exception, Cache cache) {
                log.warn("缓存清空失败：cache={}, err={}", cache.getName(), exception.getMessage());
            }
        };
    }
}
