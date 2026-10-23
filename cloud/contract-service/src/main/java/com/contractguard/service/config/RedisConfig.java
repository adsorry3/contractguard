package com.contractguard.service.config;

import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.time.Duration;

/**
 * Redis 缓存配置：JSON 序列化 + 5 分钟 TTL + key 前缀 cg:java:。
 * 只缓存读多写少的合同详情；Redis 挂掉时靠 CacheErrorHandler 降级走数据库。
 */
@Configuration
@EnableCaching
public class RedisConfig {

    /** 缓存 key 前缀，与 Python 侧（cg:task:* / cg:report:*）区分，避免冲突 */
    private static final String KEY_PREFIX = "cg:java:";

    /** 默认 TTL：5 分钟兜底，即使忘了失效也会自动过期 */
    private static final Duration DEFAULT_TTL = Duration.ofMinutes(5);

    /** RedisTemplate：key 用 String，value 用 JSON（可读，非 JDK 二进制）。 */
    @Bean
    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory factory) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(StringRedisSerializer.UTF_8);
        template.setHashKeySerializer(StringRedisSerializer.UTF_8);
        GenericJackson2JsonRedisSerializer valueSerializer =
                new GenericJackson2JsonRedisSerializer(cacheObjectMapper());
        template.setValueSerializer(valueSerializer);
        template.setHashValueSerializer(valueSerializer);
        template.afterPropertiesSet();
        return template;
    }

    /** RedisCacheManager：统一 TTL、JSON 序列化、key 前缀。 */
    @Bean
    public RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        GenericJackson2JsonRedisSerializer valueSerializer =
                new GenericJackson2JsonRedisSerializer(cacheObjectMapper());

        RedisCacheConfiguration config = RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(DEFAULT_TTL)
                .prefixCacheNameWith(KEY_PREFIX)
                .serializeKeysWith(RedisSerializationContext.SerializationPair
                        .fromSerializer(StringRedisSerializer.UTF_8))
                .serializeValuesWith(RedisSerializationContext.SerializationPair
                        .fromSerializer(valueSerializer))
                .disableCachingNullValues();

        return RedisCacheManager.builder(factory).cacheDefaults(config).build();
    }

    /** 缓存专用 ObjectMapper：注册 JavaTimeModule 处理 LocalDateTime，保留类型信息以便反序列化回 VO。 */
    private ObjectMapper cacheObjectMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        mapper.activateDefaultTyping(
                BasicPolymorphicTypeValidator.builder().allowIfSubType(Object.class).build(),
                ObjectMapper.DefaultTyping.NON_FINAL,
                JsonTypeInfo.As.PROPERTY
        );
        return mapper;
    }
}
